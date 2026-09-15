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

**Ollama runs on the Windows host, not in WSL.** WSL uses NAT networking, so `localhost:11434` is unreachable from WSL; the host answers on the default gateway: `curl http://$(ip route show default | awk '{print $3}'):11434/api/tags` (the IP changes on reboot). The `ollama` Python client honours `OLLAMA_HOST`; `src/vision/orchestrator.py` hardcodes `localhost` and does not. Models pulled as of 2026-09-15: `llama3` (8B Q4_0), `llava` (7B Q4_0), `minicpm-v` (7.6B Q4_0). **There is no embedding model** — `nomic-embed-text` (the `OllamaEmbedder` default) must be pulled before indexing can work.

**Rules for agents:**
- **Ask the user first** before: loading Marker/Surya models, sending more than a handful of items to a local LLM/VLM, running `main.py` over a whole input directory (can mean hours of GPU time), pulling Ollama models, or installing/upgrading ML packages (torch, CUDA, transformers, marker, surya). Don't edit Windows-side settings (`.wslconfig`, Ollama config) — suggest the change instead.
- **Never on this machine:** vLLM, SGLang, TGI or Docker-based model servers; `marker-pdf>=1.0` / `surya-ocr>=0.7`; models above ~8B parameters at Q4 (~5–6 GB VRAM).
- **One GPU-heavy workload at a time.** Marker's models and an Ollama model compete for the same 12 GB; on Windows/WSL, overflow can spill into shared system memory and crawl instead of failing cleanly.
- **Keep Marker's `batch_multiplier` at 1–2.** It comes from the PDF rule's `params.batch_size`, which defaults to 4 in `src/extract/pdf.py` and is set to 4 in `config_template.yaml`.
- The Gemini free tier is heavily rate-limited (see `VLM_API_RESEARCH.md`); don't loop per-image or per-chunk API calls.
- Check `nvidia-smi` and `free -h` before GPU work. Smoke-test with `--file` on a small text-layer PDF, with OCR and summarisation disabled.
- Safe to run freely: `pytest`, PyMuPDF / `pymupdf4llm` on CPU (~0.25 s/page in layout mode, ~600 MB RAM; `page_chunks=True` yields `metadata["page_number"]`), MarkItDown.

**Corpus shape (`data/raw`, 2026-09-15):** 44 PDFs, ~5,700 pages. 34 have a usable text layer (including four apparent copies of *Eberron Campaign Guide*); 10 VTM "(revised)" clanbooks are image-only scans that genuinely need OCR (`Gangrel (revised)` has a text layer, probably embedded OCR of unknown quality). Only `Toreador (revised)` has reached `data/output`; the vector DBs are effectively empty.

## Commands

```bash
source .venv/bin/activate
# pip install -r requirements.txt   # first-time setup only; ask before re-running (touches torch/marker)

# ETL (dedup -> extract -> OCR -> clean) into io.directories.staging, then io.directories.output.
# Indexing (chunk -> optional summaries -> embed -> upsert) runs in the same invocation when
# `indexing.enabled: true`; summaries additionally need `summarisation.enabled: true`.
python main.py config/<profile>.yaml
python main.py config/<profile>.yaml --file "data/raw/<collection>/<book>.pdf"   # single file, skips dedup

# Tests: CPU-only, temp dirs. tests/ is untracked, there is no pytest.ini, async tests need @pytest.mark.asyncio.
python -m pytest -q tests/
```

`config/` is gitignored and the default `config/config.yaml` doesn't exist, so pass a profile explicitly. `config_template.yaml` is the only profile matching the current schema — but it enables Marker on GPU, `async_batch` OCR, indexing and summarisation, and its Qdrant `path` is a Windows path (on Linux it resolves to a `C:/...` folder under the project root). `config_eberron.yaml`, `config_vtm.yaml` and `config_vtm_clean.yaml` use legacy keys (`pipeline.mode`, `strip_regex`, …) that are silently ignored; `vtm_test.yaml` still names a non-existent `UniversalExtractor` fallback.

**README vs. reality:** `main.py` takes the config path as a positional argument — there is no `--config` or `--action` flag; phases are gated by config booleans. `scripts/generate_master_config.py`, `scripts/resolve_batches.py` and `config/master_template.yaml` were deleted in commit `a6de4e6` (recover with `git show 216d610:<path>`), but the README still documents them.

## Architecture

### Two pipelines, chained through the filesystem

1. **`IngestionPipeline`** (`src/pipeline.py`) — dedup, extract, OCR, clean. Reads `io.input_targets`, writes markdown + YAML frontmatter to `io.directories.staging`, then writes the finished file to `io.directories.output`.
2. **`IndexingPipeline`** (`src/index/pipeline.py`) — reads markdown from `io.directories.output`, chunks, optionally generates hierarchical summaries via `SummarisationPipeline` (`src/summary/pipeline.py`), embeds, and upserts to a vector store.

`main.py` runs them in sequence. `IndexingPipeline` and `SummarisationPipeline` re-read the YAML as a raw dict via `initialize(config_path)` instead of taking the validated `Config`, so `load_config()` defaults/migrations don't apply there. Indexing processes every file concurrently (`asyncio.gather`) and uses random UUIDs as chunk IDs, so re-running it duplicates everything. There is no query/retrieval code yet.

### Resumable state machine via frontmatter

`IngestionPipeline.process_file` stores `pipeline_phases: [extract, ocr, clean]` in each staged file's frontmatter, reloads it on every run, and only runs the missing phases; a file already in the output dir is skipped. Caveats:
- A phase is recorded even when the step did nothing: `process_ocr` returns `False` both on success and on every failure path, so `ocr` in `pipeline_phases` doesn't prove OCR happened (Toreador's 189 image links resolve to no files, yet `ocr` is recorded).
- Staged/output files are keyed by filename stem only; same-named files in different folders collide.

### OCR modes (`src/vision/orchestrator.py`)

`passthrough` (default) does nothing. `local_vlm` posts each image to Ollama synchronously (hardcoded `localhost`, no timeout). `async_batch` is meant to write a `.jobstate` under `io.directories.batch_jobs`, submit a Gemini batch, return `True` (suspend) and poll on the next run — but it cannot work as written: `batches.create()` lacks the required `model=`, job states are compared to lowercase strings instead of `JobState.JOB_STATE_*`, results are read from a non-existent `job.output_uri` (they're under `job.dest`), and the JSONL is written with literal `\n` separators. `sync_live` is a stub. The image-link regex `!\[.*?\]\((.*?)\)` breaks on paths containing `)`, e.g. `Toreador (revised)`.

### Registries + config, not conditionals

Every pluggable stage implements an ABC from `src/core/interfaces.py` and is registered by string name:
- `src/extract/registry.py` — `EXTRACTOR_REGISTRY`, selected per extension by `DocumentRouter` (`src/extract/factory.py`) from `config.file_rules[".ext"].extractor`. `fallback` is used only when the primary name is missing from the registry, not when extraction fails. The router constructs a **new extractor per file**, so `PdfExtractor` reloads all Marker models for every PDF.
- `src/index/registry.py` — `CHUNKER_REGISTRY`, `EMBEDDER_REGISTRY`, `VECTORSTORE_REGISTRY`.
- Summariser selection is inline in `src/summary/pipeline.py` (`OllamaSummariser` / `GeminiSummariser`).

**To add a format/chunker/embedder/store, don't edit `IngestionPipeline`/`IndexingPipeline`:** add a class implementing the interface, register it, and reference it by name from config.

### Config system

`src/config/settings.py` defines the `Config` schema; `load_config()` resolves relative config paths against the project root and migrates legacy `pipeline.targets`/`pipeline.output_dir` into `io.*`. Unknown keys are silently ignored (no `extra="forbid"`). Parsed but never used: per-extension `file_rules.*.cleanup_rules` (only the global `cleanup_rules` is applied), `save_intermediate`/`intermediate_suffix`, `io.directories.assets` (extractors write assets to `<staging>/../assets`), and `pipeline.dynamic_cleaner`. `DynamicLLMCleaner` and `DocumentRouter._check_pdf_text_density` exist but are never called.

### Known hazard: over-escaped string literals

Several files contain `"\\n"` where a newline was intended: `src/pipeline.py` (frontmatter — output files start with a literal `---\n`), `src/vision/orchestrator.py`, `src/extract/docx.py` (whole DOCX output lands on one line), `src/extract/image.py`, and `main.py`; `image.py`/`html.py` also use `"\\\\"` for a single backslash. Find them with `grep -rnF '\\n' --include=*.py src main.py`. The existing test only asserts `"clean" in result`, so it doesn't catch this.

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
