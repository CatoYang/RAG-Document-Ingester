# Primer

A configuration-driven document ingestion pipeline that prepares heterogeneous files (PDF, Office docs, HTML, images, archives) for Retrieval-Augmented Generation. The current corpus is tabletop RPG sourcebooks (Vampire: The Masquerade, Eberron). Stages are chosen through string-keyed registries + Pydantic-validated YAML config, rather than conditionals in the pipeline code.

This is a half-built experiment, not a finished product - see `TODO.md` for what's actually done vs. still open, and `CLAUDE.md` for this machine's hardware limits (an earlier pass tried to run models this hardware can't handle and stalled the project for weeks).

```
This project was a quick experiment into RAG but i came into a lot of cleaning issues with old PDFs, poorly scanned documents that required OCR.  
Because of that i found that i ran into processing times going into several hours per document.   
Cleaning was also problematic as each document was inconsistent and standardisation meant having several steps for verification, intervention for each batch 

Even before i started indexing strategies i had to spend a lot more time configuring different methods to transcribe documents into markdown.  
I had aimmed to have this pipeline work at enterprise and local environments so i had to consider using Local models for OCR as well as processing using APIs.  

Also tried to utilise free APIs by doing batch processing of extracted images to feed into the APIs for text extraction as extracting images within the PDFs quickly ran into problems with requests per minute limits.  

Then im realising that feeding the visual models a high DPI image of the entire page is a waste of processing and have to build a new substep to extract out text regions to save on processing....

Currently reworking the framework and testing applimentation with claude code.

---

## Architecture Overview

Two pipelines, chained through the filesystem:

### `IngestionPipeline` (`src/pipeline.py`)
Filters exact duplicates using a Size + SHA-256 hash deduplicator, then converts diverse file formats (PDFs, Word docs, spreadsheets, HTML, presentations, archives, images, ebooks) into standardized Markdown, optionally OCRs embedded images, and applies regex-based cleanup. Reads `io.input_targets`, writes staged Markdown + YAML frontmatter to `io.directories.staging`, then the finished file to `io.directories.output`. Resumable: each staged file's frontmatter records which phases (`extract`/`ocr`/`clean`) already ran, so a re-run only does what's missing.

### `IndexingPipeline` (`src/index/pipeline.py`)
Reads Markdown from `io.directories.output`, chunks it by Markdown headers (falling back to recursive character splitting for oversized sections), optionally generates hierarchical document/section summaries via `SummarisationPipeline` (`src/summary/pipeline.py`), embeds each chunk, and upserts into a vector store. Re-running it is idempotent - chunks get a deterministic ID derived from `(filename, level, section, chunk_index)`, so re-indexing overwrites rather than duplicates.

`main.py` runs both pipelines in sequence; each phase is gated by config booleans (`pipeline.steps.*.enabled`, `indexing.enabled`, `summarisation.enabled`). There is no `--action` flag - `main.py` takes the config path as a positional argument.

```mermaid
graph TD
    A[Raw Documents\ndata/raw] --> PRE[Deduplicator\nSize + SHA-256 Hash]
    PRE --> B[IngestionPipeline]
    B --> C{DocumentRouter}

    C -->|Text-layer PDF| D1[PyMuPDF4LLMExtractor\nCPU, fast]
    C -->|Scanned PDF| D2[PdfExtractor\nMarker/Surya, GPU]
    C -->|Word/Excel/HTML/PPTX| E[Structured Extractors]
    C -->|Archives| F[ArchiveUnpacker]

    D1 --> G[OCR orchestrator\nimage links only]
    D2 --> G
    E --> G
    G --> H[DocumentCleaner\nregex sweep]

    H --> I[Staging Markdown\ndata/staging, data/output]

    I --> J[IndexingPipeline]
    J --> K[MarkdownChunker]
    K --> L[OllamaEmbedder]
    L --> M[Vector Store\nChromaDB/Qdrant]
```

`AutoPdfExtractor` (the recommended `.pdf` extractor - see Path 1.5 in `TODO.md`) measures each PDF's text density up front and only routes to Marker/Surya for image-only scans, so the 34 of 44 PDFs in the current corpus that already have a text layer never touch the GPU.

---

## Project Structure

```text
├── main.py                     # CLI entry point - runs IngestionPipeline then IndexingPipeline
├── query.py                    # Minimal CLI: embed a question, search the vector store, print hits
├── eval_golden.py              # Retrieval recall harness against eval/golden_qa.yaml
├── config/                     # Configuration profiles (gitignored - not checked in)
│   └── config_template.yaml    # Reference profile matching the current schema
├── TODO.md                     # Backlog and open issues, in priority order
├── CLAUDE.md                   # Actual (not aspirational) architecture notes + hardware limits
├── data/
│   ├── raw/                    # Place raw files here, organized by campaign/type
│   ├── staging/                # Intermediate markdown mid-pipeline
│   ├── output/final_markdown/  # Finished markdown, ready for indexing
│   └── dbs/                    # Vector databases (ChromaDB, Qdrant)
├── tests/                      # pytest suite (gitignored - local only)
└── src/
    ├── core/
    │   └── interfaces.py       # Base classes: BaseExtractor, BaseChunker, BaseEmbedder,
    │                           # BaseVectorStore, Document, Chunk, SearchResult
    ├── config/
    │   └── settings.py         # Pydantic schema (extra="forbid" - unknown keys raise, not vanish)
    ├── extract/
    │   ├── factory.py          # DocumentRouter: extension -> extractor, cached per (class, params)
    │   ├── registry.py         # EXTRACTOR_REGISTRY
    │   └── ...                 # One module per format (pdf, pdf_text, pdf_auto, docx, html, ...)
    ├── clean/
    │   ├── cleaner.py          # DocumentCleaner - static regex/whitespace/dedup sweep
    │   └── dynamic_cleaner.py  # DynamicLLMCleaner - LLM-proposed regexes; not wired into the
    │                           # pipeline yet, see TODO.md's Cross-Cutting section
    ├── vision/
    │   ├── orchestrator.py     # OCR modes: passthrough, local_vlm, async_batch, sync_live (stub)
    │   └── batch_manager.py    # Async batch job submission/polling (Gemini/OpenAI/Anthropic)
    ├── summary/
    │   └── pipeline.py         # Hierarchical summariser (Ollama/Gemini), gated by summarisation.enabled
    └── index/
        ├── chunkers.py         # MarkdownChunker
        ├── embedders.py        # OllamaEmbedder
        ├── vectorstores.py     # ChromaDBStore, QdrantStore
        └── registry.py         # CHUNKER_REGISTRY, EMBEDDER_REGISTRY, VECTORSTORE_REGISTRY
```

---

## Getting Started

### Prerequisites
1. **WSL2** (Ubuntu) or native Linux.
2. **Python 3.12+**.
3. **Ollama**, reachable from wherever the pipeline runs. Pull `nomic-embed-text` (embedding) and whichever chat/vision model your OCR/summarisation config names (e.g. `minicpm-v`, `llama3`). If Ollama runs on a different host than the pipeline (e.g. Windows host, WSL client), set `OLLAMA_HOST` rather than relying on `localhost`.

### Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> [!IMPORTANT]
> **Dependency pinning.** `marker-pdf==0.3.10` and `surya-ocr==0.6.13` are pinned deliberately: `marker-pdf>=1.0` swaps the native PyTorch layout/OCR models for the `surya-ocr-2` VLM behind a vLLM server, which is not viable on modest single-GPU hardware. See `CLAUDE.md` for this project's actual measured hardware limits before running anything GPU-heavy - it documents a specific incident where an earlier pass ignored this and broke the environment.

### Config profiles
`config/` is gitignored; there is no default `config/config.yaml`. Copy `config/config_template.yaml` (or write your own matching the schema in `src/config/settings.py`) to a profile of your choice and pass its path explicitly.

---

## Usage

```bash
# Full run: dedup -> extract -> OCR -> clean -> (chunk -> embed -> upsert if indexing.enabled)
python main.py config/<profile>.yaml

# Single file, skips dedup - the recommended way to smoke-test a new config
python main.py config/<profile>.yaml --file "data/raw/<collection>/<book>.pdf"

# Once something is indexed: ask a question, see which file/page/section matched
python query.py config/<profile>.yaml "what is the weakness of the Ahrimanes bloodline?"

# Chat UI: answers from the retrieved chunks only, with [n] citations and the chunks shown alongside.
# Needs the chat model pulled in Ollama (`chat.model`, default llama3); `chat.top_k` / `chat.temperature` are optional.
streamlit run app.py -- config/<profile>.yaml

# Retrieval recall against a hand-written question set (see eval/golden_qa.example.yaml)
python eval_golden.py config/<profile>.yaml eval/golden_qa.yaml
```

Toggle individual phases via `pipeline.steps.{extract,ocr,clean}.enabled`, and indexing/summarisation via `indexing.enabled` / `summarisation.enabled`.

---

## Configuration

Everything is driven by string-keyed registries + a YAML profile validated against `src/config/settings.py`'s Pydantic schema (`extra="forbid"`: an unknown or misspelled key raises at load time instead of being silently dropped).

### Extractor routing
```yaml
file_rules:
  .pdf:
    extractor: "AutoPdfExtractor"      # routes to PyMuPDF4LLMExtractor (fast, CPU) or
    fallback: "MarkItDownExtractor"    # PdfExtractor/Marker (GPU) based on measured text density
    params:
      min_avg_chars_per_page: 100
      ocr_extractor: "PdfExtractor"
      ocr_params:
        device: "cuda"
        batch_size: 2                  # keep at 1-2 on constrained GPUs - see CLAUDE.md
```
`fallback` is only used when `extractor` names a class missing from `EXTRACTOR_REGISTRY`, not when extraction itself fails.

### Cleaner module
```yaml
cleanup_rules:
  regex_removals:
    - '(?im)^.*The image shows.*$'
```
`DynamicLLMCleaner` (LLM-proposed regex sweeps with a blast-radius safety check) exists and is tested (`tests/test_cleaning.py`) but isn't wired into `IngestionPipeline` yet - see `TODO.md`.

### Indexing setup
```yaml
indexing:
  enabled: true
  chunker:
    type: "MarkdownChunker"
  embedder:
    type: "OllamaEmbedder"
    params:
      model: "nomic-embed-text"
  vectorstore:
    type: "ChromaDBStore"              # or QdrantStore
    params:
      persist_directory: "data/dbs/chromadb"
      collection_name: "text_corpus"
```

---

## Extending the Framework

Adding a new file format, chunker, embedder, or vector store never means editing `IngestionPipeline`/`IndexingPipeline`. Instead:
1. Implement the relevant interface from `src/core/interfaces.py`.
2. Register the class by name in the matching `registry.py`.
3. Reference it by that name from a config profile.

See `TODO.md` for the current backlog and priority order (stabilisation → minimum viable pipeline → retrieval quality → OCR the scanned corpus → query interface).
