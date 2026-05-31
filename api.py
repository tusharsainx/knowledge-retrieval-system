import os
import uuid
import logging
import asyncio
import boto3
from botocore.config import Config
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from arq import create_pool
from arq.connections import RedisSettings
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, VectorParams, SparseVectorParams
import google.generativeai as genai
from config import settings
from models import Document, get_db, engine, Base
import cohere

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_gateway")

# Initialize FastAPI
app = FastAPI(
    title="Production RAG Ingestion & Q&A Gateway",
    description="Zero-memory cloud-parity RAG Backend powered by Gemini, Cohere, Qdrant Cloud, and arq.",
    version="1.0"
)



GEMINI_API_KEY = settings.GEMINI_API_KEY
COHERE_API_KEY = settings.COHERE_API_KEY
QDRANT_URL = settings.QDRANT_URL
QDRANT_API_KEY = settings.QDRANT_API_KEY
REDIS_URL = settings.REDIS_URL

S3_ENDPOINT_URL = settings.S3_ENDPOINT_URL
S3_ACCESS_KEY = settings.S3_ACCESS_KEY
S3_SECRET_KEY = settings.S3_SECRET_KEY
S3_BUCKET_NAME = settings.S3_BUCKET_NAME


# 3. Client Initializations
# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Configure Async Cohere Client
cohere_client = cohere.AsyncClient(api_key=COHERE_API_KEY) if COHERE_API_KEY else None

# Configure Async Qdrant Client
qdrant_client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY) if QDRANT_URL else None

# Initialize standard boto3 client (generating presigned URLs does not block as it's local cryptographic math)
s3_client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1"
)

# 4. FastAPI Lifespan / Startup Tasks
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing system databases and queue pools...")
    
    # Create PostgreSQL tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✓ PostgreSQL metadata tables verified.")

    # Initialize MinIO / S3 Bucket
    try:
        logger.info(f"Verifying S3/MinIO bucket '{S3_BUCKET_NAME}' exists...")
        bucket_exists = False
        try:
            s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
            bucket_exists = True
        except Exception:
            pass

        if not bucket_exists:
            logger.info(f"Creating bucket '{S3_BUCKET_NAME}' in S3/MinIO...")
            s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
            logger.info(f"✓ S3/MinIO bucket '{S3_BUCKET_NAME}' created.")
        else:
            logger.info(f"✓ S3/MinIO bucket '{S3_BUCKET_NAME}' verified.")
    except Exception as e:
        logger.error(f"❌ Failed to verify/create S3 bucket: {e}")

    # Initialize arq Redis connection pool
    try:
        app.state.redis_pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        logger.info("✓ arq async queue connection initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis queue broker: {e}")
        app.state.redis_pool = None

    # Initialize Qdrant Collection with Named Hybrid Vector Config
    if qdrant_client:
        try:
            collection_name = "doc_processor_collection"
            if not await qdrant_client.collection_exists(collection_name):
                logger.info(f"Creating named hybrid vector collection '{collection_name}' in Qdrant Cloud...")
                await qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(size=3072, distance=Distance.COSINE)  # gemini-embedding-001
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams()  # Native BM25 persists
                    }
                )
                logger.info("✓ Qdrant collection created successfully.")
        except Exception as e:
            logger.error(f"❌ Qdrant Cloud connection/initialization error: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    if hasattr(app.state, "redis_pool") and app.state.redis_pool:
        await app.state.redis_pool.close()
        logger.info("arq queue pool closed.")

# 5. Pydantic Schemas
class PresignedUrlRequest(BaseModel):
    filename: str

class QueryRequest(BaseModel):
    query: str

# ══════════════════════════════════════════════════════════════════════
# PART 1: DOCUMENT INGESTION ENDPOINTS (ADMIN FLOW)
# ══════════════════════════════════════════════════════════════════════

@app.post("/documents/upload-url")
async def get_presigned_upload_url(req: PresignedUrlRequest, db: AsyncSession = Depends(get_db)):
    """Generates an S3/MinIO presigned PUT URL and registers the document state as PENDING_UPLOAD."""
    document_id = uuid.uuid4()
    s3_key = f"uploads/{document_id}/{req.filename}"

    try:
        # Generate the presigned URL (valid for 15 minutes)
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": S3_BUCKET_NAME,
                "Key": s3_key,
                "ContentType": "application/pdf"
            },
            ExpiresIn=900  # 15 mins
        )
    except Exception as e:
        logger.error(f"Failed to generate presigned S3 URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize storage destination")

    # Record document intent in PostgreSQL
    doc = Document(
        id=document_id,
        filename=req.filename,
        s3_key=s3_key,
        status="PENDING_UPLOAD"
    )
    db.add(doc)
    await db.commit()

    return {
        "document_id": str(document_id),
        "filename": req.filename,
        "upload_url": presigned_url,
        "s3_key": s3_key
    }

@app.post("/documents/{document_id}/confirm")
async def confirm_document_upload(document_id: str, db: AsyncSession = Depends(get_db)):
    """Confirms file exists in S3/MinIO and enqueues arq task with Transactional Outbox resilience."""
    doc_uuid = uuid.UUID(document_id)
    
    # Retrieve document from database
    result = await db.execute(select(Document).where(Document.id == doc_uuid))
    doc = result.scalar_one_or_none()
    print(f"Document retrieved from DB for confirmation: {doc.to_dict() if doc else 'None'}")
    if not doc:
        raise HTTPException(status_code=404, detail="Document record not found")

    if doc.status == "QUEUED":
        return {"status": "queued", "document_id": document_id, "message": "Document is already queued"}

    # Verify S3/MinIO contains the file
    try:
        metadata = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=doc.s3_key)
        doc.file_size_bytes = metadata.get("ContentLength", 0)
    except Exception as e:
        logger.error(f"File verification failed in S3 for {doc.s3_key}: {e}")
        raise HTTPException(status_code=400, detail="File could not be verified in storage. Please upload first.")

    # Transactional Outbox pattern attempt
    if app.state.redis_pool is None:
        # Broker is offline. Postpone and mark queuing failed
        doc.status = "QUEUING_FAILED"
        await db.commit()
        return JSONResponse(
            status_code=202,
            content={
                "status": "received_processing_delayed",
                "document_id": document_id,
                "message": "Upload verified. System is experiencing high load; processing will start shortly."
            }
        )

    try:
        # Attempt to queue the arq task
        await app.state.redis_pool.enqueue_job("process_document", str(doc_uuid))
        
        # Enqueued successfully
        doc.status = "QUEUED"
        await db.commit()
        return {"status": "queued", "document_id": document_id, "message": "Successfully queued for parsing and embedding"}
        
    except Exception as e:
        logger.critical(f"Queue connection failed while queuing doc {document_id}: {e}")
        # Broker failed mid-request. Recover via outbox
        doc.status = "QUEUING_FAILED"
        await db.commit()
        return JSONResponse(
            status_code=202,
            content={
                "status": "received_processing_delayed",
                "document_id": document_id,
                "message": "Upload verified. Queue offline. Processing scheduled for recovery."
            }
        )

@app.get("/documents/{document_id}/status")
async def get_document_status(document_id: str, db: AsyncSession = Depends(get_db)):
    """Returns the current ingestion status of a document."""
    doc_uuid = uuid.UUID(document_id)
    result = await db.execute(select(Document).where(Document.id == doc_uuid))
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return doc.to_dict()

# ══════════════════════════════════════════════════════════════════════
# PART 2: SEMANTIC Q&A ENGINE ENDPOINT (USER FLOW)
# ══════════════════════════════════════════════════════════════════════

# Simple word tokenizer for BM25 calculations
def tokenize(text: str) -> list[str]:
    import re
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).split()

def get_token_hash_index(token: str) -> int:
    import zlib
    return zlib.adler32(token.encode("utf-8")) % 1_000_000

def compute_sparse_vector(text: str) -> dict:
    from collections import Counter
    tokens = tokenize(text)
    counts = Counter(tokens)
    total_tokens = len(tokens)

    indices = []
    values = []
    
    for token, count in counts.items():
        idx = get_token_hash_index(token)
        tf = count / total_tokens if total_tokens > 0 else 0
        indices.append(idx)
        values.append(float(tf))

    return {
        "indices": indices,
        "values": values
    }

@app.post("/search")
async def search_and_generate(req: QueryRequest):
    """Executes dense + sparse hybrid query, reranks via Cohere, and streams cited response from Gemini."""
    if not GEMINI_API_KEY or not COHERE_API_KEY or not qdrant_client:
         raise HTTPException(status_code=500, detail="Cloud API integrations not fully configured in environment.")

    collection_name = "doc_processor_collection"
    
    try:
        # 1. Generate dense query embedding via Gemini (3072 dimensions)
        embed_response = await asyncio.to_thread(
            genai.embed_content,
            model="models/gemini-embedding-001",
            content=req.query
        )
        query_vector = embed_response["embedding"]

        # 2. Compute sparse query vector using feature hashing
        sparse_dict = compute_sparse_vector(req.query)

        # 3. Query Qdrant Cloud using native hybrid prefetch & RRF fusion (Dense + Sparse)
        # We retrieve the top 10 hybrid hits.
        search_results = await qdrant_client.query_points(
            collection_name=collection_name,
            prefetch=[
                models.Prefetch(
                    query=query_vector,
                    using="dense",
                    limit=20
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_dict["indices"],
                        values=sparse_dict["values"]
                    ),
                    using="sparse",
                    limit=20
                )
            ],
            query=models.FusionQuery(
                fusion=models.Fusion.RRF
            ),
            limit=10
        )
        
        candidates = [
            {
                "id": str(hit.id),
                "text": hit.payload.get("text", ""),
                "source": hit.payload.get("source_filename", "unknown"),
                "chunk_index": hit.payload.get("chunk_index", 0),
                "score": hit.score
            }
            for hit in search_results.points
        ]

        if not candidates:
            return JSONResponse(content={"answer": "I could not find any relevant documents in the database.", "citations": []})

        # 4. Rerank the top 10 candidates using Cohere Rerank API (0MB local RAM)
        documents_to_rerank = [c["text"] for c in candidates]
        rerank_response = await cohere_client.rerank(
            model="rerank-english-v3.0",
            query=req.query,
            documents=documents_to_rerank,
            top_n=5
        )

        # Map Cohere results back to our candidates
        reranked_candidates = []
        for result in rerank_response.results:
            idx = result.index
            cand = candidates[idx]
            cand["rerank_score"] = result.relevance_score
            reranked_candidates.append(cand)

        # 5. Format prompt with citations and stream the answer from Gemini 1.5 Flash
        context_str = ""
        for rank, chunk in enumerate(reranked_candidates):
            context_str += f"\n--- Context Source: {chunk['source']} (Page/Chunk: {chunk['chunk_index']}) ---\n"
            context_str += f"{chunk['text']}\n"

        prompt = f"""
You are a highly precise, factual Q&A assistant. Answer the user's query based ONLY on the provided context below.

Instructions:
1. Cite the source filename and chunk index for every claim you make (e.g., "[annual_report.pdf, Page 3]").
2. If the context does not contain the answer, say "I do not have enough information in the provided context to answer."
3. Do NOT make up any facts outside of the provided context.

=== CONTEXT START ===
{context_str}
=== CONTEXT END ===

User Query: {req.query}

Answer:
"""

        # Use gemini-2.5-flash as the latest active, high-performance text generation model
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        
        # Generator for server-sent streaming response
        async def response_streamer():
            import sys
            logger.info("Streaming response chunks to client & stdout:")
            # Run model generation in a background thread to prevent async loop block
            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
                stream=True
            )
            for chunk in response:
                if chunk.text:
                    sys.stdout.write(chunk.text)
                    sys.stdout.flush()
                    yield chunk.text
            sys.stdout.write("\n")
            sys.stdout.flush()

        return StreamingResponse(response_streamer(), media_type="text/plain")

    except Exception as e:
        logger.error(f"Search pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Search pipeline error: {str(e)}")
