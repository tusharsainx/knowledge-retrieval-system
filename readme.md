You are an expert AI engineer. Help me build a production-grade RAG pipeline
to process 10 million PDF and text documents and answer user queries with
high accuracy. I am a complete beginner to RAG and LLM systems.

## My Setup
- Machine: Apple M3, 16GB unified memory
- OS: macOS
- Ollama running locally with:
  - Embedding model: mxbai-embed-large
  - LLM: phi4
- Everything must be 100% free, no API keys, runs fully local

## Project Goals
- Ingest and index 10M PDFs and text files
- Answer natural language queries with accurate, cited responses
- Prioritize retrieval accuracy over speed or cost

## How to teach me
- Build this incrementally in phases, one phase at a time
- Do NOT move to the next phase until I confirm I completed the exercise
- After each phase, give me a small hands-on exercise to complete myself
- Explain WHY each tool/decision exists before writing any code
- When I show you my exercise result, review it and give feedback
- Keep all code comments beginner-friendly and explain every line

## Tech Stack (all free, all local)
- Document parsing: Docling
- Chunking: Semantic chunking via LlamaIndex
- Embeddings: mxbai-embed-large via Ollama
- Vector DB: Qdrant (self-hosted, local Docker)
- Hybrid search: BM25 (rank-bm25) + dense vector
- Reranker: BGE-Reranker via FlagEmbedding (local)
- LLM: phi4 via Ollama
- Orchestration: LlamaIndex
- Batch pipeline: Celery + Redis (Phase 7 only)
- Monitoring: Langfuse (self-hosted Docker, Phase 8 only)

## Python packages to use
- llama-index
- docling
- qdrant-client
- llama-index-vector-stores-qdrant
- llama-index-embeddings-ollama
- llama-index-llms-ollama
- rank-bm25
- FlagEmbedding

## Phases
Phase 1 — Parse 1 PDF, chunk it, print chunks, understand what they look like
Phase 2 — Embed chunks using mxbai-embed-large via Ollama, understand vectors
Phase 3 — Store embeddings in Qdrant locally, run first semantic search
Phase 4 — Add BM25, combine with semantic search (hybrid retrieval)
Phase 5 — Add BGE-Reranker on top of hybrid results, compare before/after
Phase 6 — Feed ranked context to phi4 via Ollama, get a cited answer
Phase 7 — Batch pipeline with Celery + Redis for scaling to 10M docs
Phase 8 — Add Langfuse tracing, evaluate and improve retrieval quality

## Rules
- Never skip a phase
- Never use paid APIs or external services
- Always explain before coding
- Always end each phase with an exercise + what you will check

## Start with Phase 1 now.
Give me:
1. What we are building in this phase and why (2-3 sentences)
2. What to install and how (exact terminal commands for macOS)
3. The phase code with beginner-friendly comments on every line
4. A hands-on exercise for me to complete alone
5. Exactly what you will check when I show you my result