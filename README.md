# Primer

An enterprise-grade, configuration-driven document processing pipeline designed to prepare heterogeneous files for Retrieval-Augmented Generation (RAG). 

Built heavily upon **SOLID** principles, this framework avoids hardcoding and relies entirely on dynamic registries and a central configuration system to orchestrate file extraction, cleaning, chunking, and embedding.

```
This project was a quick experiment into RAG but i came into a lot of cleaning issues with old PDFs, poorly scanned documents that required OCR.  
Because of that i found that i ran into processing times going into several hours per document.   
Cleaning was also problematic as each document was inconsistent and standardisation meant having several steps for verification, intervention for each batch 

Even before i started indexing strategies i had to spend a lot more time configuring different methods to transcribe documents into markdown.  
I had aimmed to have this pipeline work at enterprise and local environments so i had to consider using Local models for OCR as well as processing using APIs.  

Also tried to utilise free APIs by doing batch processing of extracted images to feed into the APIs for text extraction as extracting images within the PDFs quickly ran into problems with requests per minute limits.  

Then im realising that feeding the visual models a high DPI image of the entire page is a waste of processing and have to build a new substep to extract out text regions to save on processing....

This project is continuously being developed as a tool.
```

---

## Architecture Overview

The system is cleanly divided into three major phases:

### Phase 1: Pre-processing, Extraction & Cleaning
Filters exact duplicates using a two-stage Size + SHA-256 hash deduplicator. It then converts highly diverse file formats (PDFs, Word docs, Spreadsheets, HTML, presentations, and images) into standardized, clean Markdown. It utilizes Vision Language Models (VLMs) via Ollama for complex PDFs and images, alongside robust python libraries (`pandas`, `python-docx`, `beautifulsoup4`) for text-heavy documents.

### Phase 2: Hierarchical Summarisation (Agentic RAG)
Generates high-level document and section summaries using an LLM (Ollama or Gemini) prior to chunking, ensuring semantic context is preserved for the index.

### Phase 3: Indexing
Reads the cleaned Markdown, chunks it semantically based on Markdown headers, generates embeddings, and upserts the raw chunks and hierarchical summaries into a Vector Database.

```mermaid
graph TD
    A[Raw Documents\n/data/raw] --> PRE[Deduplicator\nSize + SHA-256 Hash]
    PRE --> B[Phase 1: Ingestion Pipeline]
    B --> C{Document Router}
    
    C -->|PDF/Images| D[VLM Extractor\nOllama]
    C -->|Word/Excel/HTML| E[Structured Extractors]
    C -->|Archives| F[Archive Unpacker]
    
    D --> G[Cleaner Module\nRegex & LLM Sweep]
    E --> G
    
    G --> H[Staging Markdown\n/data/staging]
    
    H --> I[Phase 2 & 3: Indexing Pipeline]
    I --> J[Hierarchical Summarisation]
    J --> K[Markdown Chunker]
    K --> L[Ollama Embedder]
    L --> M[Vector Store\nChromaDB/Qdrant]
```

---

## Project Structure

```text
├── main.py                     # CLI Entry point
├── config/                     # Configuration directory
│   ├── config.yaml             # Default configuration profile
│   └── master_template.yaml    # Auto-generated reference of all possible config values
├── scripts/
│   └── generate_master_config.py # Script to regenerate the master template
├── TODO.md                     # Backlog, advanced RAG roadmap, and open issues
├── data/
│   ├── raw/                    # Place raw files here, organized by campaign/type
│   ├── staging/                # Cleaned, standardized markdown ready for indexing
│   └── dbs/                    # Vector databases (ChromaDB, Qdrant) and local SQL DBs
└── src/
    ├── core/
    │   └── interfaces.py       # Base classes (BaseExtractor, BaseChunker, Document, Chunk)
    ├── config/
    │   └── settings.py         # Pydantic schema enforcing config validation
    ├── extractors/
    │   └── ...                 # Dynamic routing and format-specific extractors
    ├── summarisation/
    │   └── pipeline.py         # Hierarchical summariser (Ollama/Gemini)
    ├── indexing/
    │   └── ...                 # Chunkers, Embedders, and Vector Stores
    └── utils/
        ├── cleaner.py          # Regex artifact removal
        ├── deduplicator.py     # Fast exact file duplicate filter
        └── dynamic_cleaner.py  # LLM-based hallucination cleaning
```

---

## Getting Started

### Prerequisites
1. **WSL2** (Ubuntu recommended)
2. **Python 3.12+**
3. **Ollama** installed locally (running on the host machine or within WSL). Ensure models like `minicpm-v` (for extraction) and `nomic-embed-text` (for embedding) are pulled.

### Installation
```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Usage

The CLI (`main.py`) acts as the entry point for all phases of the pipeline. You can manage multiple configuration profiles by pointing the `--config` flag to different `.yaml` files in the `config/` folder.

### 1. Run the Extraction Pipeline (Phase 1)
To run exact deduplication and convert files in `data/raw/` into cleaned markdown files in `data/staging/`:
```bash
python main.py --config config/config.yaml --action extract
```
*Note: You can control the behavior of this phase via the `pipeline.steps` setting (e.g., toggling the `extract` or `clean` steps, and setting `save_intermediate: true` to dump uncleaned raw output).*

**To run a single file:**
```bash
python main.py --config config/config.yaml --action extract --file "my_document.pdf"
```

### 2. Run the Indexing Pipeline (Phases 2 & 3)
Once your files are cleaned and sitting in `data/staging/`, summarize, chunk, and embed them into your Vector Database:
```bash
python main.py --config config/config.yaml --action index
```

---

## Configuration

This framework avoids hardcoding entirely. Everything is configurable via profiles in the `config/` directory.

### The Master Template & Hooks
The pipeline's full schema is defined by Pydantic models in `src/config/settings.py`. Whenever the code changes, a Git Pre-Commit hook automatically runs `scripts/generate_master_config.py` to rebuild the `config/master_template.yaml` file. 

You should reference `config/master_template.yaml` to see all possible options you can pass into your active `config.yaml` profile.

### Extractor Routing
You can define exact behavior based on file extensions. For example, to handle PDFs using the Google Gemini Mega-Batch architecture:
```yaml
file_rules:
  .pdf:
    extractor: "FreeTierMegaBatchExtractor" # Options: FreeTierMegaBatchExtractor, EnterpriseBatchExtractor, HybridPdfExtractor
    fallback: "PdfTextExtractor"
    params:
      vlm_model: "gemini-3.7-flash"
      dpi: 300
```

### Cleaner Module
VLM models frequently hallucinate metadata. You can apply dynamic regex sweeps to strip these out across all extracted documents, or toggle a dynamic LLM cleaner.
```yaml
cleanup_rules:
  regex_removals:
    - '(?im)^.*The image shows.*$'
```

### Indexing Setup
You can easily hot-swap your Vector Database or Embedding model by changing the string pointers:
```yaml
indexing:
  chunker:
    type: "MarkdownChunker"
  embedder:
    type: "OllamaEmbedder"
    params:
      model: "nomic-embed-text"
  vectorstore:
    type: "ChromaDBStore" # Easily swap to QdrantStore
    params:
      persist_directory: "data/dbs/chromadb"
```

---

## Extending the Framework & Roadmap

To adhere to SOLID principles, you should **never** modify the `IngestionPipeline` or `IndexingPipeline` directly to add new formats. 

Instead:
1. Create a new class inheriting from the appropriate interface in `src/core/interfaces.py`.
2. Register it in the respective `registry.py` (e.g., `EXTRACTOR_REGISTRY`).
3. Point to it in your active `config.yaml`.

### Future Roadmap
Check out the [`TODO.md`](./TODO.md) file for upcoming features and advanced RAG concepts we plan to build, including:
- **Intelligent Curation:** Semantic fuzzy deduplication and document version clustering (Supersession vs. Temporal Indexing).
- **Multi-Language Support:** Handling non-Latin character sets and integrating multilingual embedding models.
- **Diagram Handling:** VLM extraction of flowcharts into Mermaid.js.
