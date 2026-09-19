# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A configuration-driven document ingestion pipeline that prepares heterogeneous files (PDF, Office docs, HTML, images, archives) for Retrieval-Augmented Generation; the current corpus is tabletop RPG sourcebooks (Vampire: The Masquerade, Eberron). Stages are chosen through string-keyed registries + Pydantic-validated YAML config. It is a half-built experiment (see `TODO.md` and the "war story" in `README.md`): expect uncommitted work in `src/`, and expect `README.md`/`TODO.md` to describe intended rather than actual behaviour — verify against the code.

## Hardware & environment limits — read before running anything heavy

Earlier agent sessions pushed models and environments beyond this machine (the vLLM + `marker-pdf>=1.0` / `surya-ocr-2` attempt), which broke the environment and stalled the project. Leftovers: `xformers` (broken — pins torch 2.4.0) and `ray` in `.venv` (nothing depends on either), and `datalab-to/surya-ocr-2*` weights in `~/.cache/huggingface`. Don't repeat it. If you are running on a different machine (the user plans a native Ubuntu install), re-measure and update this section.

**Machine (measured 2026-09-15):**
- WSL2 Ubuntu 24.04 on Windows 11 Pro (build 22631); Ryzen 5 5600X, 6 cores / 12 threads.
- **RAM visible to WSL: 7.7 GiB + 2 GiB swap.** The host has 16 GB, but there is no `.wslconfig`, so WSL gets the 50% default. This is the tightest limit.
- **GPU: RTX 3060, 12 GB VRAM, ~1 GB already in use at idle.** The same card serves WSL and Windows processes, including Ollama.
- `.venv`: Python 3.12.3, torch 2.13.0+cu130 (CUDA works in WSL), transformers 4.57.6, marker-pdf 0.3.10, surya-ocr 0.6.13. Disk space is not a constraint.

**Ollama runs on the Windows host, not in WSL.** WSL uses NAT networking, so `localhost:11434` is unreachable from WSL; the host answers on the default gateway: `curl http://$(ip route show default | awk '{print $3}'):11434/api/tags` (the IP changes on reboot). The `ollama` Python client and `src/vision/orchestrator.py` both honour `OLLAMA_HOST`; export it before anything that talks to Ollama. Models pulled as of 2026-09-16: `nomic-embed-text` (137M F16, the `OllamaEmbedder` default), `llama3` (8B Q4_0, the `chat.model` default), `llava` (7B Q4_0), `minicpm-v` (7.6B Q4_0).

**Rules for agents:**
- **Ask the user first** before: loading Marker/Surya models, sending more than a handful of items to a local LLM/VLM, running `main.py` over a whole input directory (can mean hours of GPU time), pulling Ollama models, or installing/upgrading ML packages (torch, CUDA, transformers, marker, surya). Don't edit Windows-side settings (`.wslconfig`, Ollama config) — suggest the change instead.
- **Never on this machine:** vLLM, SGLang, TGI or Docker-based model servers; `marker-pdf>=1.0` / `surya-ocr>=0.7`; models above ~8B parameters at Q4 (~5–6 GB VRAM).
- **One GPU-heavy workload at a time.** Marker's models and an Ollama model compete for the same 12 GB; on Windows/WSL, overflow can spill into shared system memory and crawl instead of failing cleanly.
- **Keep Marker's `batch_multiplier` at 1–2.** It comes from the PDF rule's `params.batch_size`, which defaults to 4 in `src/extract/pdf.py` and is set to 4 in `config_template.yaml`.
- The Gemini free tier is heavily rate-limited (see `VLM_API_RESEARCH.md`); don't loop per-image or per-chunk API calls.
- Check `nvidia-smi` and `free -h` before GPU work. Smoke-test with `--file` on a small text-layer PDF, with OCR and summarisation disabled.
- Safe to run freely: `pytest`, PyMuPDF / `pymupdf4llm` on CPU (~0.25 s/page in layout mode, ~600 MB RAM; `page_chunks=True` yields `metadata["page_number"]`), MarkItDown.

**Corpus shape (`data/raw`, 2026-09-15):** 44 PDFs, ~5,700 pages. 33 have a usable text layer (≥100 chars/page, the `AutoPdfExtractor` threshold), including four byte-identical copies of *Eberron Campaign Guide* that dedup collapses to one. 11 are image-only scans that need OCR: 10 VTM "(revised)" clanbooks plus `eberron/Eberron Campaign Setting.pdf` (0 chars/page). `Gangrel (revised)` has a text layer (~630 chars/page), probably embedded OCR of unknown quality.

**Index state (2026-09-16):** `config/config_corpus_text.yaml` indexed every text-layer book (plus the pilot's Marker-extracted `Toreador (revised)`) into ChromaDB collection `text_corpus`: 31 documents, 15,691 chunks, in 17m46s, all on CPU plus `nomic-embed-text`. Re-running that profile is idempotent.

## Commands

```bash
source .venv/bin/activate
# pip install -r requirements.txt   # first-time setup only; ask before re-running (touches torch/marker)

# ETL (dedup -> extract -> OCR -> clean) into io.directories.staging, then io.directories.output.
# Indexing (chunk -> optional summaries -> embed -> upsert) runs in the same invocation when
# `indexing.enabled: true`; summaries additionally need `summarisation.enabled: true`.
python main.py config/<profile>.yaml
python main.py config/<profile>.yaml --file "data/raw/<collection>/<book>.pdf"   # single file, skips dedup

# Textbook source audit (TODO.md Path T1): CPU-only, reads data/raw/textbooks/_candidates/<slug>/*,
# reports a format/extraction recommendation per title; --write updates data/raw/textbooks/manifest.yaml
# (keeps the user's `decision` block). Safe to run freely.
python audit_sources.py [--book <slug>] [--write]

# Chat over the index (embeds + generates via Ollama at OLLAMA_HOST; model/top_k/temperature from `chat:`)
streamlit run app.py -- config/<profile>.yaml

# Tests: CPU-only, temp dirs, no network. No pytest.ini; async tests need @pytest.mark.asyncio.
# test_settings.py's real-profile test reads the gitignored config/, so it fails in a fresh worktree.
python -m pytest -q tests/
```

`config/` is gitignored and the default `config/config.yaml` doesn't exist, so pass a profile explicitly. Profiles: `config_template.yaml` (reference; enables Marker on GPU, `async_batch` OCR, indexing and summarisation — don't run it as-is), `config_pilot.yaml` (5-book pilot), `config_text_corpus.yaml`, and `config_corpus_text.yaml` (every text-layer PDF, the 10 scanned clanbooks excluded so Marker never loads). The legacy-key profiles were deleted.

**README vs. reality:** the README was rewritten on 2026-09-15 to match the code, but still verify. `main.py` takes the config path as a positional argument; there is no `--config` or `--action` flag. `scripts/generate_master_config.py`, `scripts/resolve_batches.py` and `config/master_template.yaml` were deleted in commit `a6de4e6` (recover with `git show 216d610:<path>`).

## Architecture

### Two pipelines, chained through the filesystem

1. **`IngestionPipeline`** (`src/pipeline.py`) — dedup, extract, OCR, clean. Reads `io.input_targets`, writes markdown + YAML frontmatter to `io.directories.staging`, then writes the finished file to `io.directories.output`.
2. **`IndexingPipeline`** (`src/index/pipeline.py`) — reads markdown from `io.directories.output`, chunks, optionally generates hierarchical summaries via `SummarisationPipeline` (`src/summary/pipeline.py`), embeds, and upserts to a vector store.

`main.py` runs them in sequence. `IndexingPipeline` and `SummarisationPipeline` re-read the YAML as a raw dict via `initialize(config_path)` instead of taking the validated `Config`, so `load_config()` defaults/migrations don't apply there. Indexing processes every file concurrently (`asyncio.gather`). Chunk IDs are deterministic (`uuid5` over filename/level/section/chunk index, `src/index/vectorstores.py`), so re-indexing overwrites rather than duplicates.

### Textbook source audit

The project is pivoting from RPG sourcebooks to textbooks (see `TODO.md`, Paths T1–T3). `audit_sources.py` + `src/audit/` measure each candidate file (PDF: provenance, text layer, TOC, printed page offset, maths fonts; EPUB: DRM, layout, headings, page-list, maths as MathML vs. LaTeX-in-`alt` images) and rank them in `src/audit/recommend.py`. It is standalone: nothing in `IngestionPipeline` reads the manifest yet. `EpubExtractor` still uses `epub2txt` (plain text, headings lost); the structure-preserving replacement is Path T2.

### Retrieval and chat

`query.py` (CLI top-k search) and `eval_golden.py` (recall harness) query the store directly. `app.py` is a Streamlit chat on top of `src/chat/rag.py`: `RagAnswerer.from_config` reuses `IndexingPipeline.initialize` for the embedder + store, retrieves `chat.top_k` chunks and streams a cited answer from `chat.model` via Ollama. Each question is independent (no session memory). All async work goes through one long-lived loop in `src/chat/async_bridge.py`: a cached `ollama.AsyncClient` is bound to the loop it first ran on, so calling `asyncio.run()` per Streamlit rerun fails on the second question with "Event loop is closed". The UI's score caption is derived from `BaseVectorStore.score_note` (`src/core/interfaces.py`, overridden per store in `src/index/vectorstores.py`) rather than hardcoded, since ChromaDB distance (lower = closer) and Qdrant cosine similarity (higher = closer) read in opposite directions.

### Resumable state machine via frontmatter

`IngestionPipeline.process_file` stores `pipeline_phases: [extract, ocr, clean]` in each staged file's frontmatter, reloads it on every run, and only runs the missing phases; a file already in the output dir is skipped. Caveats:
- `process_ocr` returns `"completed"`, `"suspended"` (async batch pending; the file stops here and resumes next run) or `"failed"`; `ocr` is only appended to `pipeline_phases` when it wasn't suspended or failed. In `passthrough` mode it returns `"completed"` without doing anything, so `ocr` in the phases still doesn't prove images were transcribed.
- Staged/output files are keyed by filename stem only; same-named files in different folders collide.

### OCR modes (`src/vision/orchestrator.py`)

`passthrough` (default) does nothing. `local_vlm` posts each image to Ollama (host from `OLLAMA_HOST`, default `localhost`). `async_batch` writes a `.jobstate` under `io.directories.batch_jobs`, submits a Gemini batch (`src/vision/batch_manager.py`: `batches.create(model=, src=)`, `JobState.JOB_STATE_*` normalised to pending/running/succeeded/failed, results from `job.dest.file_name`), returns `"suspended"` and polls on the next run. The fixes are unit-tested with a fake `google.genai` (`tests/test_batch_manager.py`) but have never run against the real API. The image-link regex is greedy on the path, so paths containing `)` such as `Toreador (revised)` match.

### Registries + config, not conditionals

Every pluggable stage implements an ABC from `src/core/interfaces.py` and is registered by string name:
- `src/extract/registry.py` — `EXTRACTOR_REGISTRY`, selected per extension by `DocumentRouter` (`src/extract/factory.py`) from `config.file_rules[".ext"].extractor`. `fallback` is used only when the primary name is missing from the registry, not when extraction fails. The router caches one extractor instance per (class, params), so Marker models load once per run rather than once per PDF.
- `src/index/registry.py` — `CHUNKER_REGISTRY`, `EMBEDDER_REGISTRY`, `VECTORSTORE_REGISTRY`.
- Summariser selection is inline in `src/summary/pipeline.py` (`OllamaSummariser` / `GeminiSummariser`).

**To add a format/chunker/embedder/store, don't edit `IngestionPipeline`/`IndexingPipeline`:** add a class implementing the interface, register it, and reference it by name from config.

### Config system

`src/config/settings.py` defines the `Config` schema; `load_config()` resolves relative config paths against the project root and migrates legacy `pipeline.targets`/`pipeline.output_dir` into `io.*`. Every model inherits `StrictModel` (`extra="forbid"`), so an unknown or misspelled key raises at load time. `main.py` and `RagAnswerer.from_config` call `load_config`, so the raw-YAML readers are covered on those paths. Parsed but never used: per-extension `file_rules.*.cleanup_rules` (only the global `cleanup_rules` is applied), `save_intermediate`/`intermediate_suffix`, `io.directories.assets` (extractors write assets to `<staging>/../assets`), and `pipeline.dynamic_cleaner`. `DynamicLLMCleaner` is tested (`tests/test_cleaning.py`) but never called. The PDF text-density check lives in `src/extract/pdf_density.py` and drives `AutoPdfExtractor`.

### Past hazard: over-escaped string literals

Earlier code used `"\\n"` where a newline was meant (frontmatter, DOCX output, OCR JSONL). Fixed in `ee81138`. `grep -rnF '\\n' --include=*.py src main.py` should now only hit `src/clean/dynamic_cleaner.py`, where the escapes are deliberate (regex text inside the LLM prompt). Re-run that grep after editing string-heavy code.

### Dependencies (do not casually upgrade)

`marker-pdf==0.3.10` + `surya-ocr==0.6.13` are pinned deliberately: `marker-pdf>=1.0` swaps the PyTorch layout/OCR models for the `surya-ocr-2` VLM behind a vLLM server, which this machine can't run. The README's `transformers==4.41.2` pin was never compatible — marker 0.3.10 requires `transformers>=4.45.2,<5`, which is what `requirements.txt` now says. transformers was bumped to 4.57.6 on 2026-09-14, after the last successful Marker run (2026-09-12); Marker still imports, but a real conversion hasn't been re-verified. `python-dotenv` is imported by `main.py` but only installed transitively via marker; `pymupdf4llm`/`pymupdf-layout` are installed but undeclared.

## Project conventions (`.agents/AGENTS.md`)

`.agents/` was written for a different agent tool (hook matchers `write_to_file`/`replace_file_content`). Claude Code does not execute `.agents/hooks.json`; its only hook calls the deleted `scripts/generate_master_config.py`, and `.agents/scripts/check_sync_reads.py` isn't wired to anything. Treat these as conventions, not enforced checks:

- **Extensibility via registries (OCP/DIP)** — new document types/chunkers/stores are new classes + registry entries + config, not new conditionals in pipeline internals.
- **Chunks are Pydantic models with source metadata** (`Chunk`/`SourceMetadata` in `src/core/interfaces.py`). `page_number` is currently always `None` — nothing upstream produces page info.
- **Strict type hints.**
- **Async file I/O** is the stated rule, but `BaseExtractor.extract` is now synchronous and the extractors, deduplicator and OCR orchestrator all use blocking I/O. Use `aiofiles` in new async code; don't churn existing sync code just for this.
- Line endings are mixed (some files were saved with CRLF from Windows and there is no `.gitattributes`); write LF.
- From a Windows host rather than inside WSL, route commands through `wsl --cd "/home/cato/RAG Document Ingester" ...`.
