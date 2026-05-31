# Distributed Knowledge Retrieval System

A highly scalable, production-grade, and zero-cost cloud-parity **RAG (Retrieval-Augmented Generation) System**. 

The entire system is optimized for **zero local memory overhead** and **high I/O concurrency**. It uses serverless cloud APIs for all CPU/GPU-intensive modeling, and **`arq`** (asyncio-based Redis queue) for highly concurrent, memory-efficient background task processing.
---

## 🏗️ High-Level System Architecture (HLD)

The architecture is divided into two decoupled, specialized subsystems operating over the same database layer:

### Part 1: Document Upload & Ingestion Pipeline (Admin Flow)
Manages direct browser uploads via presigned S3/MinIO URLs, registers document states in a PostgreSQL metadata database, and triggers lightweight **`arq` async workers** to parse PDFs using **LlamaParse**, chunk them using **LlamaIndex**, embed using **Gemini `gemini-embedding-001`**, and upsert named dual-vectors (dense semantic vectors + sparse keyword weights) into **Qdrant Cloud**.

### Part 2: Semantic Q&A Retrieval Engine (User Flow)
Takes natural language user queries, performs hybrid vector + BM25 keyword search, refines candidates using the serverless **Cohere Rerank API**, and feeds the context to **models/gemini-2.5-flash** to stream cited markdown responses.
---

## 📝 Sequence Flows

### Part 1: Asynchronous Document Ingestion Flow

The ingestion process is fully asynchronous, bypassing server memory bottlenecks by using **S3 presigned URLs** and ensuring **resiliency against Redis broker outages** via a transactional outbox status machine in PostgreSQL.

![Document Ingestion Flow](document_ingestion.png)

---

### Part 2: Semantic Q&A Retrieval Flow

Takes a natural language user question, queries Qdrant using the same hybrid sparse/dense parameters, applies local cross-encoder reranking, and constructs a factual response using Gemini 2.5 Flash.

![Semantic Q&A Retrieval Flow](qa_reterival.png)

---

## 📦 Ingestion State Machine (Transactional Outbox)

To ensure zero task loss during Redis broker outages, documents transition through these database states:

```mermaid
stateDiagram-v2
    [*] --> PENDING_UPLOAD: POST /upload-url
    PENDING_UPLOAD --> QUEUED: POST /confirm (Queue Online)
    PENDING_UPLOAD --> QUEUING_FAILED: POST /confirm (Queue Offline)
    QUEUING_FAILED --> QUEUED: Automated Outbox Recovery Cron
    QUEUED --> PROCESSING: arq worker picks up task
    PROCESSING --> COMPLETED: Successful Parse & Indexing
    PROCESSING --> FAILED: Parse/Embed Error (Auto-retry up to 3)
```

---

## ⚙️ Setup & Environment Variables

Create a `.env` file in the root of the project:

```env
# Google Gemini API Config (For embeddings and LLM)
GEMINI_API_KEY=AIzaSy...

# LlamaParse API Config
LLAMA_CLOUD_API_KEY=llx-...

# Cohere Rerank API Config
COHERE_API_KEY=your-cohere-api-key

# Qdrant Cloud Configurations
QDRANT_URL=https://your-cluster-url.aws.qdrant.io
QDRANT_API_KEY=your-qdrant-cloud-api-key

# PostgreSQL Database URL
DATABASE_URL=postgresql://admin:admin@localhost:5432/doc_processor

# S3 / MinIO Object Storage Config
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=documents

# Redis Task Queue Config
REDIS_URL=redis://localhost:6379/0
```

---

## 🚀 Step-by-Step Local Development Execution

### 1. Spin up Local Infrastructure (Docker Compose)
Spins up MinIO (S3), Redis, and PostgreSQL locally (Qdrant is run in the cloud via Qdrant Cloud).
```bash
docker compose up -d
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run FastAPI Application Gateway
```bash
uvicorn api:app --reload --port 8000
```

### 4. Run arq Worker
```bash
arq tasks.WorkerSettings
```

### 5. Run Outbox Reconciliation Worker (Recovery Cron)
```bash
python3 outbox_poller.py
```