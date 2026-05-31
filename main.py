import os
import sys
import torch
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.core import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from rank_bm25 import BM25Okapi
from FlagEmbedding import FlagReranker
import re


def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25.
    
    BM25 works on individual words (tokens). This function:
    1. Converts text to lowercase (so "Doctor" and "doctor" are treated as the same word)
    2. Strips out all non-alphanumeric characters (punctuation, special symbols)
    3. Splits the remaining text into a list of individual words
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text.split()


def reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60
) -> list[dict]:
    """Reciprocal Rank Fusion (RRF) merges two ranked result lists into one.
    
    The idea: A chunk that appears at rank 1 in vector search and rank 3 in BM25
    should score higher than a chunk that appears at rank 10 in both.
    
    Formula for each chunk:  RRF_score = sum( 1 / (k + rank) )  across all lists
    
    The constant `k=60` (from the original RRF paper) prevents top-ranked results
    from dominating too aggressively. Higher k = more equal weighting across ranks.
    
    Args:
        vector_results: List of dicts with keys "id", "text", "source", "score"
        bm25_results:   List of dicts with keys "id", "text", "source", "score"
        k:              Smoothing constant (default 60, from the RRF paper)
    
    Returns:
        Merged list of dicts sorted by combined RRF score (highest first)
    """
    fused_scores = {}  # chunk_id -> { "score": float, "text": str, "source": str }

    # Score contributions from vector search results
    for rank, result in enumerate(vector_results):
        chunk_id = result["id"]
        rrf_contribution = 1.0 / (k + rank + 1)  # rank+1 because ranks are 0-indexed
        if chunk_id not in fused_scores:
            fused_scores[chunk_id] = {
                "score": 0.0,
                "text": result["text"],
                "source": result["source"],
                "vector_score": result["score"],
                "bm25_score": 0.0,
            }
        fused_scores[chunk_id]["score"] += rrf_contribution
        fused_scores[chunk_id]["vector_score"] = result["score"]

    # Score contributions from BM25 search results
    for rank, result in enumerate(bm25_results):
        chunk_id = result["id"]
        rrf_contribution = 1.0 / (k + rank + 1)
        if chunk_id not in fused_scores:
            fused_scores[chunk_id] = {
                "score": 0.0,
                "text": result["text"],
                "source": result["source"],
                "vector_score": 0.0,
                "bm25_score": result["score"],
            }
        fused_scores[chunk_id]["score"] += rrf_contribution
        fused_scores[chunk_id]["bm25_score"] = result["score"]

    # Sort by fused RRF score (highest first) and return
    fused_list = [
        {"id": chunk_id, **data}
        for chunk_id, data in fused_scores.items()
    ]
    fused_list.sort(key=lambda x: x["score"], reverse=True)
    return fused_list


def main():
    pdf_filename = "sample.pdf"
    collection_name = "doc_processor_collection"

    if not os.path.exists(pdf_filename):
        print(f"Error: '{pdf_filename}' not found. Please place your sample PDF here first!")
        sys.exit(1)

    print("--- Phase 4: Hybrid Retrieval (Dense Vector + BM25 Keyword Search) ---")

    # ══════════════════════════════════════════════════════════════════════
    # Step 1: Parse and Chunk Document (unchanged from Phase 3)
    # ══════════════════════════════════════════════════════════════════════
    print("\n[1/6] Parsing and Chunking PDF...")
    torch.backends.mps.is_available = lambda: False
    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options.device = "cpu"  # explicitly set CPU
    converter = DocumentConverter(
        format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options
        )
    }

    )
    parsed_doc = converter.convert(pdf_filename)
    markdown_text = parsed_doc.document.export_to_markdown()

    llama_doc = Document(text=markdown_text, metadata={"source": pdf_filename})

    embed_model = OllamaEmbedding(model_name="mxbai-embed-large", base_url="http://localhost:11434")

    splitter = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model
    )

    chunks = splitter.get_nodes_from_documents([llama_doc])
    print(f"✓ Parsed into {len(chunks)} semantic chunks.")

    # ══════════════════════════════════════════════════════════════════════
    # Step 2: Build BM25 Index over the same chunks
    # ══════════════════════════════════════════════════════════════════════
    # BM25 (Best Matching 25) is a classical information retrieval algorithm.
    # It scores documents by how often query terms appear in each document,
    # while penalizing very common words that appear everywhere (like "the", "is").
    # 
    # We build the BM25 index from the exact same semantic chunks that we store
    # in Qdrant, so both retrieval methods search over identical text segments.
    print("\n[2/6] Building BM25 keyword index over semantic chunks...")
    
    # Tokenize every chunk into a list of lowercase words for BM25
    chunk_texts = [chunk.text for chunk in chunks]
    tokenized_corpus = [tokenize(text) for text in chunk_texts]
    
    # Initialize the BM25 index with all tokenized chunks
    bm25_index = BM25Okapi(tokenized_corpus)
    print(f"✓ BM25 index built over {len(tokenized_corpus)} chunks.")

    # ══════════════════════════════════════════════════════════════════════
    # Step 3: Store embeddings in Qdrant (unchanged from Phase 3)
    # ══════════════════════════════════════════════════════════════════════
    print("\n[3/6] Connecting to local Qdrant database (localhost:6333)...")
    try:
        qdrant_client = QdrantClient(url="http://localhost:6333")

        if not qdrant_client.collection_exists(collection_name=collection_name):
            print(f"Collection '{collection_name}' not found. Creating a new one...")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            print("✓ Collection successfully created.")
        else:
            print(f"✓ Collection '{collection_name}' already exists. Skipping creation.")

        print("\n[4/6] Generating vector embeddings and inserting into Qdrant...")
        points = []
        for i, chunk in enumerate(chunks):
            vector = embed_model.get_text_embedding(chunk.text)

            point = PointStruct(
                id=i,
                vector=vector,
                payload={
                    "text": chunk.text,
                    "source": chunk.metadata["source"]
                }
            )
            points.append(point)

        qdrant_client.upsert(collection_name=collection_name, points=points)
        print(f"✓ Successfully stored {len(points)} vector chunks in Qdrant!")

        # ══════════════════════════════════════════════════════════════════
        # Step 5: Execute Hybrid Search — Vector + BM25 + RRF Fusion
        # ══════════════════════════════════════════════════════════════════
        search_query = "What is the primary objective or main topic discussed?"
        top_k = 10  # Retrieve top 10 from each to have a rich pool for reranking

        print(f"\n[5/7] Executing HYBRID search for query:\n\"{search_query}\"\n")

        # --- A) Dense Vector Search via Qdrant ---
        query_vector = embed_model.get_text_embedding(search_query)
        vector_response = qdrant_client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k
        )
        vector_results = [
            {
                "id": hit.id,
                "text": hit.payload["text"],
                "source": hit.payload["source"],
                "score": hit.score
            }
            for hit in vector_response.points
        ]

        # --- B) BM25 Keyword Search ---
        tokenized_query = tokenize(search_query)
        bm25_scores = bm25_index.get_scores(tokenized_query)
        # Get the indices of the top_k highest BM25 scores
        top_bm25_indices = sorted(
            range(len(bm25_scores)),
            key=lambda i: bm25_scores[i],
            reverse=True
        )[:top_k]

        bm25_results = [
            {
                "id": idx,
                "text": chunk_texts[idx],
                "source": pdf_filename,
                "score": float(bm25_scores[idx])
            }
            for idx in top_bm25_indices
            if bm25_scores[idx] > 0  # Only include chunks that actually matched keywords
        ]

        # --- C) Reciprocal Rank Fusion ---
        hybrid_results = reciprocal_rank_fusion(vector_results, bm25_results)

        # ══════════════════════════════════════════════════════════════════
        # Step 6: Rerank Hybrid Results using BGE-Reranker
        # ══════════════════════════════════════════════════════════════════
        print("\n[6/7] Initializing and executing local BGE-Reranker (BAAI/bge-reranker-large)...")
        # On Apple M3 CPU, use_fp16 must be False
        reranker = FlagReranker('BAAI/bge-reranker-large')
        
        candidates_to_rerank = hybrid_results[:10]
        if candidates_to_rerank:
            pairs = [[search_query, c["text"]] for c in candidates_to_rerank]
            reranker_scores = reranker.compute_score(pairs)
            
            # Handle the case where compute_score returns a single float instead of a list
            if isinstance(reranker_scores, float):
                reranker_scores = [reranker_scores]
                
            for idx, score in enumerate(reranker_scores):
                candidates_to_rerank[idx]["reranker_score"] = float(score)
                
            reranked_results = sorted(
                candidates_to_rerank,
                key=lambda x: x["reranker_score"],
                reverse=True
            )
        else:
            reranked_results = []

        # ══════════════════════════════════════════════════════════════════
        # Step 7: Print Comparison — Vector vs BM25 vs Hybrid vs Reranked
        # ══════════════════════════════════════════════════════════════════
        print("\n[7/7] Comparing retrieval methods side-by-side:\n")

        print("=" * 60)
        print("  A) VECTOR SEARCH RESULTS (Semantic Meaning)")
        print("=" * 60)
        for rank, r in enumerate(vector_results[:3]):
            print(f"  Rank {rank+1} | Cosine Score: {r['score']:.4f}")
            print(f"  Text: {r['text'].strip()[:200]}...")
            print("-" * 60)

        print(f"\n{'=' * 60}")
        print("  B) BM25 SEARCH RESULTS (Keyword Matching)")
        print("=" * 60)
        if bm25_results:
            for rank, r in enumerate(bm25_results[:3]):
                print(f"  Rank {rank+1} | BM25 Score: {r['score']:.4f}")
                print(f"  Text: {r['text'].strip()[:200]}...")
                print("-" * 60)
        else:
            print("  No BM25 matches found for this query.")

        print(f"\n{'=' * 60}")
        print("  C) HYBRID RESULTS (RRF Fusion of Vector + BM25)")
        print("=" * 60)
        for rank, r in enumerate(hybrid_results[:3]):
            print(f"  Rank {rank+1} | RRF Score: {r['score']:.4f} "
                  f"(Vector: {r['vector_score']:.4f}, BM25: {r['bm25_score']:.4f})")
            print(f"  Text: {r['text'].strip()[:200]}...")
            print("-" * 60)

        print(f"\n{'=' * 60}")
        print("  D) BGE-RERANKED RESULTS (Deep Cross-Encoder Relevance)")
        print("=" * 60)
        if reranked_results:
            for rank, r in enumerate(reranked_results[:3]):
                print(f"  Rank {rank+1} | Reranker Score: {r['reranker_score']:.4f} "
                      f"(RRF Score: {r['score']:.4f})")
                print(f"  Text: {r['text'].strip()[:200]}...")
                print("-" * 60)
        else:
            print("  No reranked results (empty candidate pool).")

        print(f"\n✓ Hybrid retrieval + reranking complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("\nPlease ensure Qdrant is running in Docker and Ollama is serving mxbai-embed-large.")

if __name__ == "__main__":
    main()

