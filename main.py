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

def main():
    pdf_filename = "sample.pdf"
    collection_name = "doc_processor_collection"
    
    if not os.path.exists(pdf_filename):
        print(f"Error: '{pdf_filename}' not found. Please place your sample PDF here first!")
        sys.exit(1)
        
    print("--- Phase 3: Storing and Searching Embeddings in Qdrant Local ---")
    
    # Step 1: Parse and Chunk Document
    # macOS MPS (Metal Performance Shaders) does not support float64 operations.
    # To prevent runtime crashes, we explicitly configure Docling to run on CPU.
    print("\n[1/5] Parsing and Chunking PDF...")
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
    
    # Step 2: Initialize Qdrant Client
    print("\n[2/5] Connecting to local Qdrant database (localhost:6333)...")
    try:
        qdrant_client = QdrantClient(url="http://localhost:6333")
        
        # Step 3: Check and Create Qdrant Collection
        # Production check: Only create the collection if it does not already exist.
        # This prevents overwriting and losing previously indexed documents!
        if not qdrant_client.collection_exists(collection_name=collection_name):
            print(f"Collection '{collection_name}' not found. Creating a new one...")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            print("✓ Collection successfully created.")
        else:
            print(f"✓ Collection '{collection_name}' already exists. Skipping creation and keeping existing data.")
        
        # Step 4: Generate Embeddings and Upsert to Qdrant
        print("\n[4/5] Generating vector embeddings and inserting into Qdrant...")
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
        
        # Step 5: Execute first semantic search query
        search_query = "What is the primary objective or main topic discussed?"
        print(f"\n[5/5] Executing first semantic search for query:\n\"{search_query}\"")
        
        # Embed the query using our local Ollama model
        query_vector = embed_model.get_text_embedding(search_query)
        
        # Use query_points() for pre-computed vectors.
        # qdrant_client.query() is a high-level FastEmbed wrapper that expects raw text.
        # query_points() is the lower-level method that accepts our own pre-computed vectors.
        search_result = qdrant_client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=2
        )
        print(f"✓ Search executed successfully! Here are the top results: {search_result}")
        print("\n=== Top 2 Semantic Search Results from Qdrant ===\n")
        for rank, hit in enumerate(search_result.points):
            print(f"Rank {rank+1} (Score: {hit.score:.4f})")
            print(f"Source Text: {hit.payload['text'].strip()[:300]}...")
            print("-" * 50 + "\n")
            
    except Exception as e:
        print(f"\n❌ Qdrant Connection Error: {e}")
        print("\nPlease ensure you have started Qdrant locally in Docker using:")
        print("  docker run -p 6333:6333 qdrant/qdrant")

if __name__ == "__main__":
    main()
