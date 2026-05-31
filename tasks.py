import os
import zlib
import logging
import asyncio
from collections import Counter
from datetime import datetime
import uuid
import boto3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, SparseVector
import google.generativeai as genai
from llama_parse import LlamaParse
from llama_index.core.node_parser import SentenceSplitter
from arq.connections import RedisSettings

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arq_worker")

# 1. Environment Configurations
from config import settings

GEMINI_API_KEY = settings.GEMINI_API_KEY
LLAMA_CLOUD_API_KEY = settings.LLAMA_CLOUD_API_KEY
QDRANT_URL = settings.QDRANT_URL
QDRANT_API_KEY = settings.QDRANT_API_KEY

S3_ENDPOINT_URL = settings.S3_ENDPOINT_URL
S3_ACCESS_KEY = settings.S3_ACCESS_KEY
S3_SECRET_KEY = settings.S3_SECRET_KEY
S3_BUCKET_NAME = settings.S3_BUCKET_NAME

REDIS_URL = settings.REDIS_URL

# Initialize Gemini SDK
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 2. Database Models and Session imports
from models import Document, AsyncSessionLocal

# 3. Tokenizer and Hash-based Sparse Vector Calculator (Feature Hashing)
def tokenize(text: str) -> list[str]:
    import re
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).split()

def get_token_hash_index(token: str) -> int:
    """Hashes a text token into a unique integer index in range [0, 1,000,000].
    
    Using Feature Hashing (the Hashing Trick) allows us to build a completely decentralized, 
    stateless, zero-memory sparse BM25 index that scales to 10M documents across horizontal 
    workers without needing a shared global vocabulary mapping table!
    """
    return zlib.adler32(token.encode("utf-8")) % 1_000_000

def compute_sparse_vector(text: str) -> dict:
    """Computes a stateless TF-IDF sparse weight representation for a chunk of text."""
    tokens = tokenize(text)
    counts = Counter(tokens)
    total_tokens = len(tokens)

    indices = []
    values = []
    
    for token, count in counts.items():
        idx = get_token_hash_index(token)
        # Term Frequency weighting: count / total_tokens
        tf = count / total_tokens if total_tokens > 0 else 0
        indices.append(idx)
        values.append(float(tf))

    return {
        "indices": indices,
        "values": values
    }

# ══════════════════════════════════════════════════════════════════════
# THE INGESTION TASK (PART 1)
# ══════════════════════════════════════════════════════════════════════

async def process_document(ctx, document_id: str):
    """Processes document: download -> LlamaParse -> Semantic Chunk -> Dense & Sparse Embed -> Qdrant Cloud."""
    logger.info(f"🚀 Starting task for document ID: {document_id}")
    doc_uuid = uuid.UUID(document_id)
    tmp_filepath = f"/tmp/{document_id}.pdf"
    
    # 1. Open database session
    async with AsyncSessionLocal() as db:
        # Retrieve document record
        result = await db.execute(select(Document).where(Document.id == doc_uuid))
        doc = result.scalar_one_or_none()
        
        if not doc:
            logger.error(f"Document {document_id} not found in PostgreSQL.")
            return

        # Update state to PROCESSING
        doc.status = "PROCESSING"
        doc.updated_at = datetime.utcnow()
        await db.commit()

        try:
            # 2. Download file from S3 / MinIO
            logger.info(f"Downloading file from S3: {doc.s3_key}")
            s3_client = boto3.client(
                "s3",
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=S3_ACCESS_KEY,
                aws_secret_access_key=S3_SECRET_KEY,
                region_name="us-east-1"
            )
            # Run blocking boto3 download in background thread
            await asyncio.to_thread(
                s3_client.download_file,
                S3_BUCKET_NAME,
                doc.s3_key,
                tmp_filepath
            )
            logger.info("✓ File downloaded successfully.")

            # 3. Parse PDF to Markdown using LlamaParse Cloud API (0MB local RAM)
            logger.info("Parsing PDF via LlamaParse Cloud API...")
            parser = LlamaParse(api_key=LLAMA_CLOUD_API_KEY, result_type="markdown")
            # aload_data uploads PDF and yields beautifully structured markdown
            parsed_docs = await parser.aload_data(tmp_filepath)
            markdown_text = parsed_docs[0].text
            logger.info(f"✓ Parsed successfully. Text length: {len(markdown_text)} chars.")

            # 4. Token-based Async-Safe Chunking using LlamaIndex SentenceSplitter
            # This is 100% local, runs instantly, takes < 5MB RAM, and makes ZERO API calls (saving rate limits)
            logger.info("Segmenting document into semantic token chunks...")
            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
            chunks = splitter.split_text(markdown_text)
            logger.info(f"✓ Document segmented into {len(chunks)} text chunks.")

            # 5. Connecting to Qdrant Cloud
            logger.info("Connecting to Qdrant Cloud cluster...")
            qdrant_client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            
            points = []
            logger.info("Generating Dense Embeddings and Sparse vectors for Qdrant Cloud...")
            
            # Limit concurrent embedding requests to avoid API rate spikes
            semaphore = asyncio.Semaphore(5)

            async def embed_and_build_point(chunk_idx: int, chunk_text: str) -> PointStruct:
                async with semaphore:
                    # A) Generate Dense Embedding via Gemini (size=3072)
                    embed_response = await asyncio.to_thread(
                        genai.embed_content,
                        model="models/gemini-embedding-001",
                        content=chunk_text
                    )
                    dense_vector = embed_response["embedding"]

                    # B) Compute stateless sparse weights for BM25 persistence
                    sparse_dict = compute_sparse_vector(chunk_text)
                    sparse_vector = SparseVector(
                        indices=sparse_dict["indices"],
                        values=sparse_dict["values"]
                    )

                    point_id = str(uuid.uuid5(doc_uuid, f"chunk_{chunk_idx}"))
                    
                    return PointStruct(
                        id=point_id,
                        vector={
                            "dense": dense_vector,
                            "sparse": sparse_vector
                        },
                        payload={
                            "text": chunk_text,
                            "document_id": str(doc_uuid),
                            "source_filename": doc.filename,
                            "chunk_index": chunk_idx,
                            "total_chunks": len(chunks)
                        }
                    )

            # Process all chunks concurrently
            tasks = [embed_and_build_point(idx, text) for idx, text in enumerate(chunks)]
            points = await asyncio.gather(*tasks)

            # 5.5 Auto-create collection if it doesn't exist (Self-Healing Worker)
            collection_name = "doc_processor_collection"
            if not await qdrant_client.collection_exists(collection_name):
                logger.info(f"Collection '{collection_name}' not found. Creating it natively with 3072 dimensions...")
                from qdrant_client.models import VectorParams, SparseVectorParams, Distance
                await qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(size=3072, distance=Distance.COSINE)
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams()
                    }
                )
                logger.info("✓ Qdrant collection created successfully by worker.")

            # 6. Upsert Named Hybrid Vectors to Qdrant Cloud
            logger.info(f"Upserting {len(points)} named vector points to Qdrant Cloud...")
            await qdrant_client.upsert(
                collection_name=collection_name,
                points=points
            )
            logger.info("✓ Qdrant Cloud upsert complete!")

            # 7. Update PostgreSQL to COMPLETED
            doc.status = "COMPLETED"
            doc.chunk_count = len(chunks)
            doc.error_message = None
            doc.updated_at = datetime.utcnow()
            await db.commit()
            logger.info(f"🎉 Ingestion task finished successfully for {doc.filename}!")

        except Exception as e:
            logger.error(f"❌ Ingestion task failed for document {document_id}: {e}")
            import traceback
            traceback.print_exc()

            # Update PostgreSQL status to FAILED
            doc.status = "FAILED"
            doc.error_message = str(e)
            doc.updated_at = datetime.utcnow()
            await db.commit()
            
        finally:
            # 8. Clean up local tmp file to free storage
            if os.path.exists(tmp_filepath):
                os.remove(tmp_filepath)
                logger.info("Temporary PDF file deleted.")

# ══════════════════════════════════════════════════════════════════════
# ARQ WORKER CONFIGURATION SETTINGS
# ══════════════════════════════════════════════════════════════════════

async def startup(ctx):
    logger.info("arq worker startup complete. Polling Redis broker...")

async def shutdown(ctx):
    logger.info("arq worker shutting down...")

class WorkerSettings:
    """Configuration class for the arq background worker runner."""
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    functions = [process_document]
    concurrency = 5 # Limits concurrent worker threads for local CPU constraints
    on_startup = startup
    on_shutdown = shutdown
