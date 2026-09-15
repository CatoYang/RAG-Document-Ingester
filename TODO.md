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
- [x] **Fix config/registry mismatches** — `config_eberron.yaml`, `config_vtm.yaml`, `config_vtm_clean.yaml` (legacy `pipeline.mode`/`targets`/`output_dir`/`strip_regex` shape) and `vtm_test.yaml` (referenced a `UniversalExtractor` fallback never in `EXTRACTOR_REGISTRY`) deleted 2026-09-15 rather than migrated — `config_template.yaml`, `config_text_corpus.yaml` and `config_pilot.yaml` already cover the current schema's shape, so migrating dead files added nothing. All three are gitignored (local-only), so this wasn't a tracked-file change.
- [x] **Over-escaped newline literals** — `src/pipeline.py`, `main.py`, `src/vision/orchestrator.py`, `src/extract/image.py`, `src/extract/docx.py`, `src/extract/html.py` had `"\\n"`/`"\\\\"` where a real newline/backslash was intended (frontmatter, DOCX tables, and console output all landed on one line). Fixed 2026-09-15, covered by `test_save_document_writes_real_newlines`.
- [x] **OCR phase falsely marked complete on failure** — `process_ocr` returned the same `bool` whether OCR succeeded, found nothing to do, or failed outright, so `IngestionPipeline` recorded `"ocr"` as done on every non-suspended path. Now returns a tri-state result (`"completed"`/`"suspended"`/`"failed"`); only `"completed"` advances `pipeline_phases`. Fixed 2026-09-15, covered by `test_ocr_failure_does_not_advance_pipeline_phase`. (Note: `async_batch`'s "succeeded"/"failed" status strings still won't match the real `google.genai.types.JobState.JOB_STATE_*` enum — see the Gemini batch item below — so the tri-state plumbing is correct but that specific mode still can't reach "completed" via a real API response yet.)
- [x] **Image-link regex broke on filenames containing `)`** — `!\[.*?\]\((.*?)\)` is non-greedy, so it truncated the captured path at the first `)` — which happens inside folder names like `Toreador (revised)`. Replaced with `_find_image_links()`, matching greedily to the last `)` on the line (images are one-per-line in current extractor output). Fixed 2026-09-15, covered by `test_find_image_links_handles_parentheses_in_path`.
- [x] **`local_vlm` OCR mode hardcoded `localhost:11434`** — unreachable from WSL, where Ollama runs on the Windows host. Now reads `OLLAMA_HOST`. Fixed 2026-09-15, covered by `test_process_ocr_local_vlm_honours_ollama_host_env`.
- [x] **Gemini batch mode is non-functional** — fixed 2026-09-15, all three named bugs plus a related one found while fixing them: `BatchManager.submit_job` now passes the required `model=` to `client.batches.create()` (confirmed required via `inspect.signature` against the installed `google-genai`, not just the TODO's word for it); `check_status` now reads `job.state.name` (a `JobState` enum member, not a string) through a per-provider normalization map down to `"pending"/"running"/"succeeded"/"failed"`, rather than comparing the raw enum to lowercase string literals; `download_results` reads `job.dest.file_name` via `client.files.download()` instead of the nonexistent `job.output_uri` (confirmed `BatchJob` has no such field via the installed SDK's Pydantic model fields). The related bug: `src/vision/orchestrator.py`'s own status comparisons (`"processing"`, `"finished"`, etc.) never matched any provider's real vocabulary either — now compares against the normalized set instead. The JSONL-literal-`\n` concern turned out to already be fixed by the earlier over-escaped-newline pass (`ee81138`). Untested against a real Gemini batch job (no API key/quota here) — covered instead by `tests/test_batch_manager.py`, which mocks the SDK at the `sys.modules` level.
- [x] **`DocumentRouter` reloads Marker per file** — a new `PdfExtractor` (and its Marker model set) was instantiated for every PDF in `process_targets`. `DocumentRouter` now caches extractor instances keyed by `(extractor class, json.dumps(params))`, so the same extractor+params combination is only constructed once per router lifetime. Fixed 2026-09-15, covered by `tests/test_factory.py` (including a regression test for nested-dict params like `AutoPdfExtractor`'s `ocr_params`, which broke an earlier `tuple(sorted(params.items()))`-based cache key).
- [x] **Config accepts unknown/misspelled keys silently** — every model in `src/config/settings.py` now inherits from a shared `StrictModel` (`model_config = ConfigDict(extra="forbid")`), so a typo'd or legacy key raises a `ValidationError` at `load_config()` instead of vanishing. Safe now that the legacy config files above are gone; verified `config_template.yaml`, `config_text_corpus.yaml` and `config_pilot.yaml` all still load unchanged. Fixed 2026-09-15, covered by `tests/test_settings.py`.
- [x] **Indexing re-runs duplicate the vector store** — `ChromaDBStore`/`QdrantStore` upserted with a fresh `uuid.uuid4()` per chunk every call. Both now derive a stable point ID from `(filename, level, section, chunk_index)` via `_deterministic_id()` (`src/index/vectorstores.py`), so re-indexing the same file overwrites instead of duplicating. Fixed 2026-09-15, covered by `tests/test_vectorstores.py`. `IndexingPipeline.process_directory` still has no per-file completed-tracking of its own (unlike the ETL pipeline's frontmatter state machine) — it just re-embeds and re-upserts every file in the output directory on every run, which is now at least idempotent rather than duplicating, but still wasteful for large corpora (see Path 6).

### Missing Dependencies
- [x] **Reconcile `requirements.txt`** — `pymupdf`, `python-docx`, `beautifulsoup4`, `markdownify`, `pandas`, `tabulate`, `requests`, `pytest`, `pytest-cov`, `pytest-asyncio` are now declared. `transformers` is pinned to `>=4.45.2` (marker-pdf 0.3.10's actual floor — the old README pin of `==4.41.2` never worked).
- [x] **`pymupdf4llm`/`pymupdf-layout`** — now declared in `requirements.txt` (used by `PyMuPDF4LLMExtractor`, Path 1.5). `python-dotenv` (imported by `main.py`, previously only present transitively via `marker-pdf`) added explicitly too.
- [x] **Remove `xformers` and `ray`** from the venv — done 2026-09-15 (`pip uninstall -y xformers ray`); confirmed neither had a reverse dependency (`pip show` empty `Required-by`) before removing. `pip check` reports no broken requirements now.

### Test Suite
- [x] **Set up test infrastructure** — `tests/` exists with `conftest.py` fixtures (`temp_workspace`, `mock_config`) and `pytest-asyncio`.
- [x] Regression test for the frontmatter idempotency state machine (`test_pipeline_idempotency`).
- [x] **Regression tests for the newline/OCR-status/regex fixes above** — see `tests/test_vision_orchestrator.py` and the two new tests in `tests/test_pipeline.py`.
- [x] **Unit tests for each extractor** — `tests/test_extractors.py` (2026-09-15) covers every registry entry not already tested by the Path 1.5 test modules: `DocxExtractor`, `HtmlExtractor`, `ImageExtractor`, `SpreadsheetExtractor`, `PresentationExtractor`, `MarkItDownExtractor`, `ArchiveUnpacker`, `EpubExtractor`, `OpenOfficeExtractor`, `PdfExtractor`. The last two mock their heavy external dependency (LibreOffice subprocess, Marker's model loading) rather than exercising it for real — loading Marker needs asking the user first per `CLAUDE.md`, and LibreOffice may not even be installed on a given machine; these tests only need to prove each extractor wires that dependency's output into a `Document` correctly.
- [x] **Integration tests for cleaning pipeline** — `tests/test_cleaning.py` (2026-09-15) covers `DocumentCleaner` (the regex/whitespace/paragraph-dedup rules actually wired into `IngestionPipeline`'s clean phase) plus `DynamicLLMCleaner` exercised directly with a mocked LLM call, since it still isn't reachable from any pipeline path (see Cross-Cutting section) — including its confidence threshold and blast-radius safety checks, which had no coverage at all before.
- [x] **Integration tests for indexing pipeline** — `tests/test_indexing_pipeline.py` (2026-09-15) drives the real `IndexingPipeline.process_directory` (real `MarkdownChunker`, real `ChromaDBStore` against a tmp_path DB, only the embedder faked to avoid needing Ollama), including that re-running it is idempotent end-to-end through the pipeline (not just at the vectorstore layer, which `tests/test_vectorstores.py` already covered) and that frontmatter is parsed into metadata rather than embedded as text.

### Documentation
- [x] **`CLAUDE.md` rewritten (2026-09-15)** to describe actual behaviour (not README's aspirational `--action`/master-config-template interface) and to record this machine's hardware limits.
- [x] **Update `README.md`** — rewritten 2026-09-15 to describe actual behaviour: dropped the `--action extract|index` flag and `scripts/generate_master_config.py`/`config/master_template.yaml` references (both scripts were deleted in commit `a6de4e6`; recoverable via `git show 216d610:<path>` if the master-template workflow is worth rebuilding later), corrected the project structure listing to match `src/`'s actual module names, added `query.py`/`eval_golden.py` usage, and noted `DynamicLLMCleaner`'s not-yet-wired status. Left the user's own "war story" section as written.

---

## Path 1.5: 🚀 Minimum Viable Pipeline on the Text-Layer Corpus

> New path. Goal: get from "nothing has been queried, ever" to "I can ask a question and see which book/page it came from" using the 34 of 44 PDFs that already have a text layer (measured 2026-09-15) — no OCR, no GPU, no Gemini quota needed. This is what makes Path 2's "retrieval quality" work measurable instead of guesswork.

- [x] **`PyMuPDF4LLMExtractor`** (`src/extract/pdf_text.py`) — CPU-only Markdown extraction via `pymupdf4llm.to_markdown(path, page_chunks=True)` (measured ~0.25s/page, ~600MB RAM). Registered in `EXTRACTOR_REGISTRY`. Emits a `<!-- page_number: N -->` marker before each page's text (deliberately not the uppercase `<!-- PAGE N -->` format some configs' `cleanup_rules.regex_removals` already strip, which predates this and targeted an unrelated artifact) so chunking can recover per-page provenance. Fixed 2026-09-15, covered by `tests/test_pdf_text.py`.
- [x] **Text-density routing** — rather than wiring the standalone `DocumentRouter._check_pdf_text_density` (written, never called) directly into the router, the density check moved to a shared utility (`src/extract/pdf_density.py`) and backs a new composing extractor, **`AutoPdfExtractor`** (`src/extract/pdf_auto.py`, registered in `EXTRACTOR_REGISTRY`): measures each PDF's text density and delegates to `PyMuPDF4LLMExtractor` or lazily-loaded `PdfExtractor`/Marker. `DocumentRouter._check_pdf_text_density` removed as dead code (superseded). New profile `config/config_text_corpus.yaml` points `.pdf` at it. Fixed 2026-09-15, covered by `tests/test_pdf_density.py` and `tests/test_pdf_auto.py` (including a check that the OCR extractor is loaded at most once per run, and not at all when every PDF has a text layer).
- [x] **Carry `page_number` through chunking** — `MarkdownChunker._consume_page_markers` now parses `PyMuPDF4LLMExtractor`'s page markers out of each chunk's text (stripping them from the stored/embedded text), assigning the last page number seen so far to that chunk and carrying it forward for chunks that fall between two markers. Extractors that don't emit page markers still work; `page_number` just stays `None` for them, as before. Fixed 2026-09-15, covered by `tests/test_chunkers.py`.
- [x] **Pull `nomic-embed-text`** — done 2026-09-15, pulled remotely via `POST http://<gateway-ip>:11434/api/pull` (no Windows-side access needed - the Ollama server was already running and reachable). Confirmed present in `/api/tags` (274MB).
- [x] **Fix duplicate-ID upserts** — see Path 1.
- [x] **Drop empty chunks before embedding** — turned out not to be a mere "nice to have": running the pilot below against a real Ollama host hit it immediately. `OllamaEmbedder` returns a **zero-length embedding** for an empty prompt (the empty leading chunk `MarkdownChunker` could emit), and ChromaDB's `upsert` crashes on that with `IndexError: list index out of range in upsert.` (`chromadb/api/types.py::normalize_embeddings` indexes into an empty embedding vector) - silently caught several layers up by `IndexingPipeline.process_file`'s broad `except Exception`, which just logs `[red]Failed to index <file>[/red]` with no traceback, so this would otherwise have looked like a mysterious per-file failure. `MarkdownChunker.chunk()` now skips any split whose text is empty after page-marker stripping, renumbering `chunk_index` over the kept chunks. Fixed 2026-09-15, covered by `tests/test_chunkers.py::test_chunker_drops_empty_chunks`.
- [x] **A `query.py`** (repo root) — embeds a question with the configured embedder, searches the configured vector store (`BaseVectorStore.search`, new abstract method, implemented for both `ChromaDBStore` and `QdrantStore` — see `SearchResult` in `src/core/interfaces.py`), and prints matches with filename/page/section. No UI, no chat loop. Fixed 2026-09-15, covered by `tests/test_query.py`. This is a precursor to Path 5's MVP Chat Interface, not a replacement for it.
- [ ] **A golden Q&A set (30–50 questions)** — the harness exists (`eval_golden.py`, repo root, covered by `tests/test_eval_golden.py`) and reports top-k recall against `eval/golden_qa.yaml`, but the actual questions don't: `eval/golden_qa.example.yaml` ships with placeholder entries only, deliberately not filled in with fabricated answers. **Needs a human who actually knows the VTM/Eberron content** to write 30–50 real question → (source file, page) pairs; copy the example to `eval/golden_qa.yaml` and fill it in. This becomes the yardstick for every Path 2/3 decision below — nothing there should be started until this exists.
- [x] **Pilot run against real content** — 2026-09-15: ran `config/config_pilot.yaml` (5 hand-picked text-layer PDFs - 3 VTM, 2 Eberron, 1 to 45 pages each - plus `Toreador (revised).md`, an already-extracted file left over from an earlier session, which `IndexingPipeline.process_directory` picks up automatically since it indexes everything in the output directory) end to end: extract → clean → chunk → embed → upsert, 883 chunks total, all via `AutoPdfExtractor`'s fast text-layer path (never touched Marker). Verified retrieval qualitatively with `query.py` against both collections (VTM: "weakness of the Ahrimanes bloodline" correctly surfaced `Ahrimanes.md` p.23-27; Eberron: a Sharn/Convergence Manifesto question correctly surfaced the right Eberron file) - this is a spot-check, not the golden-Q&A recall measurement above, which still needs real questions.
- [x] **Run against the rest of the text-layer corpus** — 2026-09-16: `config/config_corpus_text.yaml` lists the 33 PDFs that pass the 100 chars/page density check explicitly, so no scan can reach Marker. Its OCR extractor name is deliberately unregistered, so a misrouted file would error instead of loading Marker. One more scan turned up: `eberron/Eberron Campaign Setting.pdf` reads 0 chars/page, making 11 scans, not 10. Dedup dropped the 3 duplicate *Eberron Campaign Guide* copies. Result: 25 newly extracted PDFs, all on CPU, no failures, in 17m46s. ChromaDB `text_corpus` holds 31 documents and 15,691 chunks, and the per-file upsert counts in the log sum to exactly that, so there are no duplicates.

---

## Path 2: 🔍 Retrieval Quality (RAG Performance)

> Sequence every item here against the Path 1.5 golden Q&A set — don't build any of this speculatively.

### Search Quality
- [ ] **Hybrid search** — combine vector similarity with BM25 keyword search. Likely the single biggest win for this corpus: RPG sourcebooks are dense with proper nouns (clan names, disciplines, NPCs, locations) that embeddings alone tend to fuzz over.
- [ ] **Cross-encoder reranking** — add a reranker (e.g., `cross-encoder/ms-marco-MiniLM`) after initial retrieval.
- [ ] **Chunk overlap tuning** — experiment with overlapping windows for better context continuity.
- [x] **Drop empty/near-empty chunks before embedding** — done as part of Path 1.5 (see there); turned out to crash indexing outright rather than merely waste an embed call. Still open: *near*-empty chunks (a few words, mostly whitespace) aren't filtered, just fully-empty ones — revisit if those turn out to be noisy in practice.
- [ ] **ChromaDB collection uses L2 distance, not cosine** — found in the 2026-09-16 live check. `ChromaDBStore` calls `get_or_create_collection(name=...)` without `metadata={"hnsw:space": "cosine"}`, so scores are raw L2 distances (~177–380 observed), while `QdrantStore` uses cosine. Ranking by L2 on unnormalised vectors can differ from cosine ranking. Switching means re-creating the collection and re-indexing (~18 min). Compare both with the golden set.
- [ ] **Section metadata picks the outermost header** — `MarkdownChunker` prefers `Header 1` over `Header 2`/`Header 3`, and pymupdf4llm turns running page headers into H1s. Most *V5 Core Rules* chunks from pages 69–219 are therefore labelled `kindred _society_`, which tells the reader and the LLM nothing. Prefer the most specific header, and consider dropping headers that repeat on most pages of a book.
- [ ] **Relevance cutoff before generation** — off-corpus questions sit clearly further away than on-topic ones: "capital of France" had a best distance of 342, against 178–210 for real questions. A `chat.max_distance` that skips the LLM when nothing is close enough would stop the grounding failure noted under Path 5. Calibrate the cutoff on the golden set, not on four questions.

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
- [x] **Build chat frontend** — `app.py` (repo root), Streamlit: `streamlit run app.py -- config/<profile>.yaml`. Chat history lives in `st.session_state` for display only. Retrieval reuses `query.py`'s path (`IndexingPipeline.initialize` builds the embedder + vector store, cached with `st.cache_resource`). All async work runs on one long-lived background event loop (`src/chat/async_bridge.py`): cached `ollama.AsyncClient`s keep connections bound to their first loop, so a fresh `asyncio.run()` per Streamlit rerun fails with "Event loop is closed" on the second question. Reproduced against a stub HTTP server and covered by `tests/test_async_bridge.py`. Config problems and an unreachable Ollama/store show up as `st.error`, not a stack trace. Verified live 2026-09-16 against `text_corpus` with `llama3`, driving `app.py` through Streamlit's `AppTest`. Two questions in a row ran on the cached answerer, about 3 s each with the model warm, citations and the chunks expander both rendered, and there were no errors.
- [x] **Conversational RAG** — `src/chat/rag.py`: `RagAnswerer` embeds the question, takes the top `chat.top_k` chunks and streams an Ollama chat answer (`chat.model`, default `llama3`; `chat.temperature`, default 0.1) from a prompt of numbered context blocks. The prompt says to use only that context, cite `[n]`, and say plainly when the context doesn't cover the question. Empty retrieval skips the LLM call. Each question is answered independently (no session memory, see below). Covered by `tests/test_chat_rag.py`.
- [x] **Source citation** — each context block is labelled with file, page (`page unknown` when the chunk has none) and section, and the model is told to cite `[n]`. Under every answer, an expander lists the retrieved chunks by rank with file, page, section, raw store score and full text, so a retrieval miss can be told apart from a bad generation. Citations aren't validated: nothing checks that a `[n]` exists or supports the claim.

### Known issues from the live check (2026-09-16)
- [ ] **llama3 breaks the grounding rule on off-corpus questions.** Asked "What is the capital of France?", it said the passages don't state it, then "inferred" Paris and cited two VTM chunks that mention Paris as a Camarilla city. On-corpus answers (Brujah bane, dragonmarks, Five Nations) were faithful to their chunks. Fix with the Path 2 relevance cutoff first, then tighten the prompt; an 8B model won't follow instructions perfectly.
- [ ] **No timeout on Ollama calls** — if Ollama silently stops responding, the page hangs instead of showing `st.error`.
- [ ] **Score caption is ChromaDB-specific** — `app.py` says "lower is closer", which is backwards for `QdrantStore` (cosine similarity, higher is closer). Derive the caption from the store type.

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
