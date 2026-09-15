# Development Roadmap & Backlog

> **Priority Order:** Path 1 (Stabilisation) → Path 1.5 (MVP on text-layer corpus) → Path 2 (Retrieval Quality, evaluation-driven) → Path 3 (OCR the scanned corpus) → Path 5 (Query Interface) → Path 4/6 (parked)
>
> Revised 2026-09-15: a repo re-analysis found the pipeline has never run end-to-end and there is no query/retrieval code, so "retrieval quality" work (the old Path 2) had nothing to measure against. The new Path 1.5 gets a small, real corpus queryable first; everything after it is prioritised by what a golden Q&A eval actually shows helps. See `CLAUDE.md`'s "Hardware & environment limits" section before running anything GPU-heavy — an earlier agent pushed models/environments beyond this machine and stalled the project for weeks.

---

## Path 1: 🛡️ Stabilisation & Testing (Foundation)

> Must be completed first — unblocks all other paths safely.

### Critical Bugs
- [x] **Fix async/sync mismatch** — `BaseExtractor.extract` is now `def`, not `async def`; concrete extractors are synchronous and called directly (no `asyncio.to_thread` wrapper yet — fine for now since the pipeline processes one file at a time).
- [x] **Fix syntax error** in `src/summary/providers.py` — unescaped newlines inside string literals fixed.
- [x] **Unify Gemini SDK** — `src/clean/dynamic_cleaner.py` migrated from legacy `google.generativeai` to `google.genai`, matching the rest of the codebase.
- [ ] **Fix config/registry mismatches** — `config_eberron.yaml`, `config_vtm.yaml`, `config_vtm_clean.yaml` still use the legacy `pipeline.mode`/`targets`/`output_dir`/`strip_regex` shape (only `pipeline.targets`/`pipeline.output_dir` are auto-migrated by `load_config()`; `mode` and `strip_regex` are silently dropped). `vtm_test.yaml` references a `UniversalExtractor` fallback that isn't in `EXTRACTOR_REGISTRY`. Either migrate these files to the current schema or delete them — they don't currently produce working configs.
- [ ] **Over-escaped newline literals** — `src/pipeline.py`, `main.py`, `src/vision/orchestrator.py`, `src/extract/image.py`, `src/extract/docx.py`, `src/extract/html.py` have `"\\n"`/`"\\\\"` where a real newline/backslash was intended (frontmatter, DOCX tables, and console output all land on one line).
- [ ] **OCR phase falsely marked complete on failure** — `process_ocr` returns the same `bool` whether OCR succeeded, found nothing to do, or failed outright, so `IngestionPipeline` records `"ocr"` as done on every non-suspended path. Needs a tri-state result (`"completed"`/`"suspended"`/`"failed"`) so only real completion advances `pipeline_phases`.
- [ ] **Image-link regex breaks on filenames containing `)`** — `!\[.*?\]\((.*?)\)` is non-greedy, so it truncates the captured path at the first `)` — which happens inside folder names like `Toreador (revised)`.
- [ ] **`local_vlm` OCR mode hardcodes `localhost:11434`** — unreachable from WSL, where Ollama runs on the Windows host. Should read `OLLAMA_HOST`.
- [ ] **Gemini batch mode is non-functional** — `BatchManager.submit_job` calls `client.batches.create()` without the required `model=`; `check_status` compares to lowercase strings instead of `google.genai.types.JobState.JOB_STATE_*`; `download_results` reads a nonexistent `job.output_uri` instead of `job.dest`; the JSONL writer emits literal `\n` instead of real newlines (partially covered by the newline fix above, but the request schema itself needs rework against the current `google-genai` API). Low priority until Path 3 (OCR the scans) actually needs async batch — `local_vlm` or synchronous Marker/Surya cover the corpus we have.
- [ ] **`DocumentRouter` reloads Marker per file** — a new `PdfExtractor` (and its Marker model set) is instantiated for every PDF in `process_targets`, instead of once per run. Cache extractor instances in the router (keyed by extractor class + params) before doing any multi-file Marker run.
- [ ] **Config accepts unknown/misspelled keys silently** — no `extra="forbid"` on the Pydantic models, so a typo'd or legacy config key (see above) is dropped without warning instead of raising. Add strict validation once the legacy config files are cleaned up or removed, so it doesn't just break them louder.
- [ ] **Indexing re-runs duplicate the vector store** — `ChromaDBStore`/`QdrantStore` upsert with a fresh `uuid.uuid4()` per chunk every call, so `IndexingPipeline.process_directory` (which has no completed-file tracking of its own) duplicates all chunks on a second run. Needs deterministic IDs (e.g. hash of `filename + chunk_index`) before Path 1.5 can be re-run safely.

### Missing Dependencies
- [x] **Reconcile `requirements.txt`** — `pymupdf`, `python-docx`, `beautifulsoup4`, `markdownify`, `pandas`, `tabulate`, `requests`, `pytest`, `pytest-cov`, `pytest-asyncio` are now declared. `transformers` is pinned to `>=4.45.2` (marker-pdf 0.3.10's actual floor — the old README pin of `==4.41.2` never worked).
- [ ] **`python-dotenv`** is imported directly by `main.py` but only present in the venv as a transitive dependency of `marker-pdf`; add it explicitly.
- [ ] **`pymupdf4llm`/`pymupdf-layout`** are installed (needed for Path 1.5's text-layer extractor) but undeclared in `requirements.txt`.
- [ ] **Remove `xformers` and `ray`** from the venv — leftovers from an abandoned vLLM/`surya-ocr-2` attempt; nothing in the current dependency tree requires either, and `xformers` currently pins `torch==2.4.0` (a `pip check` conflict against the installed `torch==2.13.0`).

### Test Suite
- [x] **Set up test infrastructure** — `tests/` exists with `conftest.py` fixtures (`temp_workspace`, `mock_config`) and `pytest-asyncio`.
- [x] Regression test for the frontmatter idempotency state machine (`test_pipeline_idempotency`).
- [ ] **Regression tests for the newline/OCR-status/regex fixes above** — nothing currently asserts real newlines in saved output or that a failed OCR mode doesn't get recorded as `"ocr"` complete.
- [ ] **Unit tests for each extractor** — mock file inputs, verify `Document` output structure. None exist yet beyond the one pipeline-level test.
- [ ] **Integration tests for cleaning pipeline** — static cleaner + `DynamicLLMCleaner` (currently unreachable from any pipeline path — see Cross-Cutting section).
- [ ] **Integration tests for indexing pipeline** — chunking → embedding → upsert flow, including the duplicate-ID issue above.

### Documentation
- [x] **`CLAUDE.md` rewritten (2026-09-15)** to describe actual behaviour (not README's aspirational `--action`/master-config-template interface) and to record this machine's hardware limits.
- [ ] **Update `README.md`** — still documents the `--action extract|index` flag and `scripts/generate_master_config.py`/`config/master_template.yaml`, none of which exist (both scripts were deleted in commit `a6de4e6`; recoverable via `git show 216d610:<path>` if the master-template workflow is worth rebuilding later).

---

## Path 1.5: 🚀 Minimum Viable Pipeline on the Text-Layer Corpus

> New path. Goal: get from "nothing has been queried, ever" to "I can ask a question and see which book/page it came from" using the 34 of 44 PDFs that already have a text layer (measured 2026-09-15) — no OCR, no GPU, no Gemini quota needed. This is what makes Path 2's "retrieval quality" work measurable instead of guesswork.

- [ ] **`PyMuPDF4LLMExtractor`** — new `BaseExtractor` implementation using `pymupdf4llm.to_markdown(path, page_chunks=True)` (measured ~0.25s/page, ~600MB RAM, CPU-only; produces `metadata["page_number"]` per chunk, which nothing in the pipeline currently captures). Register in `EXTRACTOR_REGISTRY`.
- [ ] **Text-density routing** — wire `DocumentRouter._check_pdf_text_density` (written, never called) into `.pdf` routing so text-layer PDFs go to the new fast extractor and only image-only scans fall through to `PdfExtractor`/Marker, or make it an explicit `file_rules[".pdf"].extractor` choice per config profile if auto-routing feels too magic.
- [ ] **Carry `page_number` through chunking** — `MarkdownChunker`/`SourceMetadata` already have the field; nothing populates it today because no extractor emits per-page metadata. Once `PyMuPDF4LLMExtractor` exists, thread its page metadata through `chunk()`.
- [ ] **Pull `nomic-embed-text`** on the Ollama host (only `llama3`, `llava`, `minicpm-v` are currently pulled — see `CLAUDE.md`).
- [ ] **Fix duplicate-ID upserts** (see Path 1 bug above) before indexing anything for real.
- [ ] **A ~50-line `query.py`** — embed a question with the same embedder, run a similarity search, print matching chunks with filename + page. No UI, no chat loop — just enough to see whether retrieval works at all. This is a precursor to Path 5's MVP Chat Interface, not a replacement for it.
- [ ] **A golden Q&A set (30–50 questions)** — hand-written questions with known-correct source book/page, covering both VTM and Eberron content. Track top-5 recall. This becomes the yardstick for every Path 2/3 decision below.

---

## Path 2: 🔍 Retrieval Quality (RAG Performance)

> Sequence every item here against the Path 1.5 golden Q&A set — don't build any of this speculatively.

### Search Quality
- [ ] **Hybrid search** — combine vector similarity with BM25 keyword search. Likely the single biggest win for this corpus: RPG sourcebooks are dense with proper nouns (clan names, disciplines, NPCs, locations) that embeddings alone tend to fuzz over.
- [ ] **Cross-encoder reranking** — add a reranker (e.g., `cross-encoder/ms-marco-MiniLM`) after initial retrieval.
- [ ] **Chunk overlap tuning** — experiment with overlapping windows for better context continuity.

### Semantic Deduplication
- [ ] **Locality-Sensitive Hashing (LSH/MinHash)** — fast pre-computation on extracted text to drop documents that are >95% similar. Immediately useful: `data/raw/eberron` already has 4 near-identical copies of *Eberron Campaign Guide* (2 in `eberron/`, 2 in `eberron/Across Eberron/`) that would otherwise get indexed 4×.
- [ ] **Vector DB cosine similarity check** — check chunks against the vector database before upserting; drop chunks if a 99% semantic match already exists.

### Document Family & Version Clustering
- [ ] **Family identification pass** — group files into "families" using name similarity, LSH, or size heuristics.
- [ ] **Routing strategy:**
  - A (Supersession) — keep only the latest version, discard older drafts
  - B (Temporal Indexing) — index all versions with chronological/version metadata

### Evaluation
- [ ] **Extend the Path 1.5 golden Q&A set** as retrieval changes land — recall/precision deltas per change, not just a one-time baseline.

---

## Path 3: 📷 OCR the Scanned Corpus

> The 10 VTM "(revised)" clanbooks (measured 2026-09-15: `Brujah`, `Toreador`, `Tremere`, `Nosferatu`, `Malkavian`, `Ravnos`, `Lasombra`, `Assamite`, `Followers of Set`, `Giovanni`) are image-only scans and need real OCR — `Gangrel (revised)` has a text layer already (likely embedded OCR of unknown quality; verify before trusting it as-is). Sequence this after Path 1.5 proves the pipeline works end-to-end on the easy 34 books, and after golden-Q&A results say whether OCR quality is actually the bottleneck for these books' content.

- [ ] **Re-verify Marker on the current `transformers` version** — the last confirmed-working Marker run (`Toreador`, 2026-09-12) predates the `transformers` 4.57.6 bump (2026-09-14). Smoke-test one short scanned PDF before trusting a full-book run.
- [ ] **One book at a time, `batch_size` 1–2, nothing else on the GPU** (see `CLAUDE.md` hardware limits) — do not run all 10 in one pass.
- [ ] **Table-aware chunking** — keep stat blocks and tables intact rather than splitting mid-row (matters more once these books are actually indexed).
- [ ] **Fix or drop the Gemini async-batch path** (Path 1 bug) if free-tier batching turns out to be worth it over local Marker/Surya for this remaining set — 10 books is small enough that local OCR may just be simpler.

---

## Path 5: 🎮 Query Interface / RAG Application

> Builds on Path 1.5's `query.py`. Bumped ahead of source-expansion and performance work — a chat interface is what actually makes retrieval-quality decisions visible to a human instead of a recall percentage.

### MVP Chat Interface
- [ ] **Build chat frontend** — Streamlit, Gradio, or FastAPI + HTML — on top of `query.py`, not a rewrite of it.
- [ ] **Conversational RAG** — retrieve relevant chunks and feed as context to LLM (Ollama local or API).
- [ ] **Source citation** — show which document/page/section each answer came from (page numbers only exist once Path 1.5's page-metadata work lands).

### Enhanced Features
- [ ] **Session memory** — maintain conversation history for multi-turn RPG Q&A.
- [ ] **GM tools** — NPC generator, encounter builder, lore lookup powered by the vector store.

---

## Path 4: 🌐 Source Expansion (parked)

> Parked until Path 1.5–3 deliver a working, evaluated pipeline on the existing 44-PDF corpus. No value in more input formats while the ones we have aren't reliably indexed yet.

### Google Drive Integration (`.gdoc`, `.gsheet`, `.gslides`)
- [ ] **Problem:** Google Workspace files synced to a local drive are merely pointer files containing web URLs, not actual data. The pipeline currently requires manual export to `.docx` or `.pdf`
- [ ] **Implement `GoogleDriveExtractor`:**
  - Set up GCP project with Google Drive API
  - OAuth 2.0 authentication
  - Parse file ID from `.gdoc` JSON stub
  - Download exported `.docx` into `tempfile.TemporaryDirectory()`
  - Pass to `MarkItDownExtractor`
  - Exclude `client_secret.json` from VCS via `.gitignore`

### Web Sources
- [ ] **Web scraping extractor** — ingest wikis (e.g., Eberron wiki, D&D Beyond) with rate limiting and dedup

### Multimedia
- [ ] **Audio/video transcription** — Whisper-based extractor for actual-play podcasts or session recordings

### Campaign Tools
- [ ] **Notion / Obsidian vault import** — for homebrew campaign notes

---

## Path 6: ⚡ Performance & Scale (parked)

> Parked. This is a single 12GB-VRAM GPU shared with the Windows host — parallel extraction and multi-document concurrency buy little until there's a queue of documents actually worth processing faster, and Marker itself is the bottleneck, not I/O.

### Pipeline Performance
- [ ] **Refactor for Asynchronous I/O** — upgrade `BaseExtractor` and all concrete implementations to fully support `async`/`aiofiles`. Deliberately deferred: `BaseExtractor.extract` was made synchronous (see Path 1, done) because nothing in the extractors was actually doing overlappable I/O; revisit only if profiling shows it matters.
- [ ] **Parallel extraction** — process multiple documents concurrently with `asyncio.gather` or a task queue. Low value alongside a single shared GPU (Marker) — most benefit would be for the non-GPU extractors (MarkItDown, docx, html, spreadsheet).
- [ ] **Incremental indexing** — only re-index changed/new documents (leverage the frontmatter state machine).
- [ ] **Streaming embeddings** — batch embed chunks rather than one-at-a-time (`OllamaEmbedder.embed` currently loops one request per text).

### Resource Management
- [ ] **GPU memory management** — better handling of Marker/Surya GPU allocation for large PDF batches (see `CLAUDE.md` — cap `batch_multiplier` at 1–2 on this hardware regardless).

### Observability
- [ ] **Progress dashboard** — Rich-based TUI or web dashboard showing pipeline progress across documents.

---

## Cleaning Capabilities (Cross-Cutting)

### Dynamic Copyright & Watermark Stripper
- [ ] **`DynamicLLMCleaner` exists but is never invoked from `IngestionPipeline`** — `pipeline.dynamic_cleaner` is parsed into `PipelineSettings` but nothing reads it. Wire it in (as an optional step after the static `DocumentCleaner`) or remove the dead code — currently it's neither used nor tested end-to-end.

### Multi-Language Support
- [ ] **Language detection** — add detection capabilities for non-English documents. Not currently needed by the VTM/Eberron corpus; revisit only if a non-English source is actually added (see Path 4).
- [ ] **Non-Latin character support** — ensure extraction handles non-Latin character sets.
- [ ] **Multilingual embeddings** — upgrade to models like `multilingual-e5` for cross-language semantic search.
