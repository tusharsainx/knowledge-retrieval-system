# Distributed Knowledge Retrieval System

A highly scalable, production-grade, and **zero-cost ($0/month)** cloud-parity **RAG (Retrieval-Augmented Generation) System** featuring a high-fidelity **React + Redux** dashboard!

The entire system is optimized for **zero local memory overhead** (consuming < 50MB RAM on all servers) and **high I/O concurrency**. It uses serverless cloud APIs for all CPU/GPU-heavy modeling, and an async-native, multi-process python container environment on **Render** paired with a global CDN frontend on **Vercel** to provide a complete web dashboard.

---

## 🏗️ High-Level System Architecture (HLD)

The system consists of three decoupled, production-grade layers:

1. **Vite + React + Redux SPA Frontend**:
   - A premium dark-mode, glassmorphic dashboard built using responsive Vanilla CSS.
   - Features **direct-to-S3 browser uploads** via presigned URLs to bypass web server bandwidth choke points.
   - Auto-polls document ingestion states, showing progress, completion chunk counts, and live worker exception popover tooltips.
   - Integrates an asynchronous **typewriter-style SSE word stream** for Gemini responses and parses citation tags into **interactive clickable pills** that slide open a retrieved context drawer.

2. **FastAPI Application Gateway & Ingestion Subprocess (Web Service)**:
   - Serves `/documents/upload-url`, `/confirm`, `/status`, and `/search` routes with full CORS compatibility.
   - **Multi-Process Container Hack**: Automatically spawns and monitors the **`arq` background task worker** as a child subprocess inside the same container during boot. This enables running both the API gateway and ingestion worker concurrently on **Render's free web tier** for $0/month!

3. **Asynchronous Ingestion Worker & Cloud Services**:
   - Uses **LlamaParse Cloud API** to extract structured markdown with zero server overhead.
   - Employs token-based sentence splitting locally via LlamaIndex.
   - Generates dense embeddings via **Gemini `gemini-embedding-001`** (3072-d).
   - Computes stateless sparse keyword weights via **stateless Feature Hashing** (BM25 trick) to scale to **10M documents** with 0MB RAM.
   - Upserts named dense and sparse vectors directly to your **Qdrant Cloud** cluster.

---

## 🌐 Productionized Cloud Services Stack ($0/Month)

The entire production footprint is deployed on free-developer tiers:

| Component                     | Cloud Provider        | Tier Details                                                              |
| :---------------------------- | :-------------------- | :------------------------------------------------------------------------ |
| **Frontend UI**               | **Vercel**            | Free static CDN hosting (Auto-built from `frontend/` root)                |
| **API Gateway & Worker**      | **Render**            | Free Python Web Service (spawns `arq` child worker process)               |
| **Relational Metadata DB**    | **Supabase Postgres** | PostgreSQL 16 (connected via IPv4-compatible Session Pooler on Port 5432) |
| **Document Storage (S3 API)** | **Supabase Storage**  | S3-Compatible Private Object Storage (1GB free)                           |
| **Task Queue Message Broker** | **Upstash Redis**     | Serverless Redis (10,000 free commands/day, SSL `rediss://`)              |
| **Hybrid Vector Database**    | **Qdrant Cloud**      | Serverless Vector DB (1GB RAM free, holding ~200k vectors)                |
| **Dense Embeddings & LLM**    | **Google AI Studio**  | `gemini-embedding-001` & `gemini-2.5-flash` (Free Tier API)               |
| **Stateless Reranker**        | **Cohere Dashboard**  | `rerank-english-v3.0` API (Free Tier API, 0MB RAM)                        |

---

## 📝 Sequence Flows

### Part 1: Asynchronous Document Ingestion Flow

The ingestion process is fully asynchronous, bypassing server memory bottlenecks by uploading directly to Supabase S3 and ensuring task queue resiliency via a transactional outbox status machine in PostgreSQL.

![Document Ingestion Flow](document_ingestion.png)

---

### Part 2: Semantic Q&A Retrieval Flow

Takes a natural language user question, queries Qdrant using the same hybrid sparse/dense parameters, applies serverless Cohere reranking, and streams a factual, cited response using Gemini 2.5 Flash.

![Semantic Q&A Retrieval Flow](qa_reterival.png)

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

# PostgreSQL Connection String (Use Session Pooler port 5432 for Render IPv4-compatibility)
DATABASE_URL=postgresql+asyncpg://postgres.your-ref:password@aws-1-your-region.pooler.supabase.com:5432/postgres

# Supabase Storage S3 Configuration (Generate keys in dashboard)
S3_ENDPOINT_URL=https://your-ref.supabase.co/storage/v1/s3
S3_ACCESS_KEY=your-generated-s3-access-key-id
S3_SECRET_KEY=your-generated-s3-secret-access-key
S3_BUCKET_NAME=documents

# Upstash Redis Connection String (Use rediss:// for secure TLS)
REDIS_URL=rediss://default:password@your-endpoint.upstash.io:6379
```

---

## 🚀 Step-by-Step Local Execution

### 1. Spin up Local Infrastructure (Docker)

Spins up Redis, and PostgreSQL locally for dev testing:

```bash
docker compose up -d
```

### 2. Run the Backend API & Worker

Activate your pyenv virtual environment and start the FastAPI gateway (which will automatically launch the `arq` task worker in the background):

```bash
source /Users/gabru/.pyenv/versions/3.11.14/envs/dp/bin/activate
uvicorn api:app --reload --port 8000
```

### 3. Run the React Frontend dev server

Navigate to the `frontend/` folder, install packages, and start the Vite server:

```bash
cd frontend
npm install
npm run dev
```

Open **`http://localhost:3000`** in your browser!
