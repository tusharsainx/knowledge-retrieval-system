import os
import sys
import torch
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import Document

def main():
    # Step 1: Ensure there is a PDF file to process
    pdf_filename = "sample.pdf"
    if not os.path.exists(pdf_filename):
        print(f"Error: '{pdf_filename}' not found in the current directory.")
        print("Please place any PDF file in this directory and rename it to 'sample.pdf', then re-run this script!")
        sys.exit(1)
        
    print(f"--- Phase 1: Parsing and Semantic Chunking for '{pdf_filename}' ---")
    
    # Step 2: Initialize Docling Converter
    # Docling is a layout-aware document parsing engine. It intelligently understands headers,
    # tables, paragraphs, and lists inside PDFs without relying on simple coordinate extraction.
    print("\n[1/4] Initializing Docling DocumentConverter...")
    # Force CPU device
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
    # Step 3: Convert PDF to structured document representation
    print(f"[2/4] Parsing PDF '{pdf_filename}' (this may take a few seconds on the first run)...")
    conversion_result = converter.convert(pdf_filename)
    
    # Export the parsed layout directly to Markdown.
    # Markdown preserves the structure (headers, bold text, lists, and tables) beautifully.
    document_markdown = conversion_result.document.export_to_markdown()
    print(f"✓ PDF successfully parsed! Raw length: {len(document_markdown)} characters.")
    
    # Step 4: Create a LlamaIndex Document object
    # LlamaIndex operates on 'Document' objects, wrapping our parsed text and metadata.
    llama_document = Document(
        text=document_markdown,
        metadata={
            "source_file": pdf_filename,
            "parser": "Docling"
        }
    )
    
    # Step 5: Set up local Embeddings via Ollama
    # Semantic chunking relies on calculating similarity between adjacent sentences.
    # We use the local mxbai-embed-large embedding model running in Ollama.
    print("\n[3/4] Connecting to local Ollama embedding service (mxbai-embed-large)...")
    embed_model = OllamaEmbedding(
        model_name="mxbai-embed-large",
        base_url="http://localhost:11434"
    )
    
    # Step 6: Initialize LlamaIndex Semantic Chunking
    # Unlike static chunking (which cuts text at a fixed number of characters or tokens),
    # a Semantic Splitter monitors the semantic shift between sentences. 
    # It creates a new chunk boundary only when the semantic difference exceeds a threshold.
    print("[4/4] Setting up SemanticSplitterNodeParser...")
    splitter = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model
    )
    
    # Step 7: Parse Document into Chunks (Nodes)
    print("Chunking document semantically...")
    try:
        nodes = splitter.get_nodes_from_documents([llama_document])
        print(f"✓ Document successfully split into {len(nodes)} semantic chunks!")
        
        # Step 8: Print the first 3 chunks to inspect
        print("\n=== Inspecting first 3 Semantic Chunks ===\n")
        for i, node in enumerate(nodes[:3]):
            print(f"--- Chunk {i+1} (Length: {len(node.text)} chars) ---")
            print(node.text.strip())
            print("-" * 50 + "\n")
            
    except Exception as e:
        print(f"\n❌ Error during semantic chunking: {e}")
        print("\nNote: Make sure Ollama is installed and running locally with:")
        print("  ollama run mxbai-embed-large")

if __name__ == "__main__":
    main()
