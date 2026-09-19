# Development Roadmap & Backlog

> **Priority Order:** Path T1 (Source Audit) → Path T2 (Textbook Extraction) → Path T3 (Textbook Chunking & Evaluation) → Path 2 (Retrieval Quality, evaluation-driven) → Path 5 (Query Interface) → parked: Path 3 (RPG OCR), Path 4, Path 6
>
> Revised 2026-09-19: the project is pivoting from RPG sourcebooks to textbooks, sourced by the user from Anna's Archive. Files there come from several upstream libraries in several forms (retail PDF, scan + OCR, Calibre conversions, retail and converted EPUB, DjVu), often several per title. So the first new step is an **audit** that measures each candidate file and records which format and extraction path to use, before any textbook is ingested. The pipeline itself (Paths 1 and 1.5, now under "Completed foundation" at the bottom) carries over unchanged, and the RPG-only work (Path 3, the RPG golden set) is parked. The existing `data/raw` RPG corpus and the `text_corpus` index are left in place.
>
> Earlier history (2026-09-15): a repo re-analysis found the pipeline had never run end-to-end, so Path 1.5 got a small real corpus queryable first, and everything after it is prioritised by what a golden Q&A eval shows actually helps. See `CLAUDE.md`'s "Hardware & environment limits" section before running anything GPU-heavy.

---

## Path T1: 🔎 Source Audit (textbooks) — current phase

> Goal: for every textbook, decide **which file** (among the Anna's Archive candidates) and **which extraction path** to use, from measured evidence rather than guesswork, and record that decision in a manifest that later runs can reuse. Everything here runs on CPU (PyMuPDF, EbookLib, zip/XML inspection) and is safe to run freely. The user sources the books; the audit only reads them.
>
> Division of labour: the user downloads 2–3 candidates per title (both PDF and EPUB where available). The script measures them and recommends a pick. The user makes the final call in the manifest.

### First findings: *Machine Learning for Text* (Springer, 2nd ed., 2026-09-19)
Both candidates are the same edition (shared eBook ISBN 9783030966232). The audit recommends the **EPUB**; it's waiting on the user's decision in the manifest.
- **EPUB** (Springer Nature EPUB3 Converter, no DRM, reflowable): real `h1`–`h4` headings in 17 of 18 content documents. Maths is PNG images, but **2,001 of 2,077 equation images carry their LaTeX source in `alt`**, which is better than MathML for RAG. The 76 without LaTeX are display equations. It has no `page-list` or page-break markers, so it gives no page citations, and the nav only lists chapters (the depth is in the headings).
- **PDF** (LaTeX-typeset, Producer/Creator metadata stripped, so the audit falls back to spotting Computer Modern fonts): clean text layer (~3,200 chars/page), 532-entry TOC to depth 4, and printed page numbers at a constant offset of 20. But its maths is flattened (`X = (x1 . . . xd)`, `√xi`), and it uses ligature characters (`ﬁ`) and hyphenates words at line ends.
- This suggests a new T2 item (below): use the EPUB for text and the PDF only as a page map.

### Intake
- [x] **Candidate folder layout** — `data/raw/textbooks/_candidates/<book-slug>/`, one folder per title with every downloaded candidate in it. `data/` is gitignored. The first two files had already been renamed to `Machine Learning for Text.{pdf,epub}`, so the Anna's Archive filename parser hasn't seen a real name yet.
- [ ] **Promotion step** — after a decision, copy the chosen file to `data/raw/textbooks/<book-slug>.<ext>` under a short, unique stem. Staged/output files are keyed by stem only, so long or clashing names would collide. Candidates are copied, never moved or deleted.

### Audit script (`audit_sources.py` at repo root, logic in `src/audit/`)
Follows the `find_document_families.py` pattern: report-only by default; `--write` updates the manifest. `--book <slug>` limits the run to one title. CPU-only; both ML4T candidates audit in ~1.5 s.
- [x] **Filename parsing** (`src/audit/filename.py`) — splits Anna's Archive `--`-separated names into title / author / year / ISBNs / md5 / other fields, classifying fields by shape rather than position. A renamed file comes back as just a title.
- [x] **Integrity** — md5 of each file, compared with the filename's md5 when there is one. Formats with no auditor (DjVu, MOBI…) and unreadable files are reported as unsupported and rejected, rather than crashing the run.
- [x] **Provenance** (`src/audit/pdf.py`, `src/audit/epub.py`; each call comes with its evidence):
  - PDF: Producer/Creator keywords (scan tools → `scan_ocr`, Calibre and similar → `converted`, typesetters → `typeset`). If there's no recognised producer, LaTeX fonts on ≥50% of sampled pages → `typeset`.
  - Scan fingerprint: a full-page image on ≥50% of sampled pages → `scan_ocr` or `scan_image_only`, whatever the metadata says.
  - EPUB: Calibre metadata or a converter in the generator or OPF comments → `converted`. A generator or publisher present → `publisher`.
- [x] **Text usability** — PDF: chars/page over 40 evenly spaced pages (not `pdf_density.py`'s first 5, which on a textbook are the cover and front matter), image-only page share, ligature characters, hyphenated line ends. EPUB: fixed vs. reflowable, and DRM (`rights.xml`, or `encryption.xml` covering more than font obfuscation).
- [x] **Structure** — PDF: TOC entry count and depth. EPUB: `h1`–`h6` counts, the share of content documents with real headings, and nav/NCX TOC entries and depth. Not done: the heading count from `pymupdf4llm`, which the TOC made unnecessary so far.
- [x] **Page citations** — PDF: page labels, plus printed page numbers found in running heads/footers and the offset between them and PDF page indices. EPUB: `page-list` entries and page-break markers.
- [x] **Maths** — EPUB: MathML count, equation images (by filename or class), and how many have LaTeX in their `alt` text; mode is `mathml` / `latex_alt_text` / `images_no_source`. PDF: share of sampled pages using maths fonts (flattened in the text layer). Still open: the "sample for the user to inspect by eye" part, which becomes part of `--sample`.
- [ ] **Figures & tables** — EPUB figure and table counts done. Still open: a PDF equivalent (caption counting), if the pilot shows it matters.
- [ ] **Back matter** — the index, glossary, bibliography and answers are found from PDF TOC titles and EPUB spine file names. Still open: uploader-inserted pages and "downloaded from" watermarks, once a real Anna's Archive file shows what they look like.
- [ ] **Same-edition check** — ISBN comparison done (`match` / `no_isbn_overlap` / `unknown`, taking ISBNs from the PDF's copyright page, the EPUB identifiers and the filename). Still open: MinHash text comparison (`src/dedup/family.py`) for candidates without ISBNs.

### Side-by-side sample
- [ ] **`--sample` mode** — extract one chosen chapter from each candidate through the real extractor and `MarkdownChunker`, then write the chunks side by side to a comparison folder. The user reads ~10 chunks per candidate; this catches garbled equations and interleaved sidebars that metrics miss. Needs the structure-preserving EPUB extractor from Path T2 first: the current `epub2txt` one would make the EPUB look worse than it is.

### Manifest & decision
- [x] **Manifest** (`data/raw/textbooks/manifest.yaml`, `src/audit/manifest.py`) — one entry per title: `decision` (file / extraction / notes, filled in by the user and kept across re-audits), `recommendation`, and full per-candidate metrics including md5s, which serve as the "dictionary" for recognising files later.
- [x] **Recommendation rule** (`src/audit/recommend.py`) — ranked tiers: good EPUB → typeset PDF → converted PDF → weak EPUB (converted, few headings, or more than 20 equation images with no source) → scan + OCR PDF → image-only PDF (Marker, with a GPU warning). DRM, fixed-layout, encrypted and unsupported files are rejected. The result carries reasons, caveats (lost equations, no page citations with a pointer to a PDF page map, ligatures, back matter), alternatives and rejections. It treats LaTeX alt text as equal to MathML. Thresholds are first guesses until the pilot calibrates them.
- [ ] **Profile generation** — build a config profile's `io.input_targets` and `file_rules` from the manifest's decisions, replacing the hand-maintained lists used for the RPG corpus.

### Tests & pilot
- [x] **Tests** — `tests/test_audit.py` (22 tests): PDFs and EPUBs generated in `tmp_path` (PyMuPDF, and hand-built EPUB zips so DRM, layout and maths can be controlled), with no network and no real books. It covers the filename parser, each provenance heuristic, DRM vs. font obfuscation, maths modes, the recommendation tiers, manifest merging that keeps the decision, and the script's report-only/`--write` behaviour.
- [ ] **Pilot** — the user sources 3–5 textbooks across different publishers and subjects (at least one maths-heavy), in both formats where available. Run the audit, read the side-by-side samples, and adjust the thresholds and rule. **Exit criterion:** every pilot title has a decision in the manifest that the user agrees with. Progress: 1 title (*Machine Learning for Text*, maths-heavy, Springer).

---

## Path T2: 📚 Textbook Extraction

> Driven by what the T1 audit shows. Don't build a handler for a case the pilot hasn't turned up.

- [ ] **Structure-preserving EPUB extractor** — `EpubExtractor` (`src/extract/epub.py`) uses `epub2txt`, which returns plain text and loses the headings, the main reason to prefer EPUB. Replace it with, or register alongside it, an extractor that walks the spine in order and converts XHTML to markdown (`EbookLib` + `markdownify`, both installed). It should keep headings, tables, lists and footnotes, and skip non-content spine items (cover, copyright, nav). Compare its output with `MarkItDownExtractor`'s EPUB support before writing much custom code.
- [ ] **EPUB page markers** — where the EPUB has a `page-list`, emit `<!-- page_number: N -->` at each page anchor, the same marker `PyMuPDF4LLMExtractor` emits, so `MarkdownChunker` fills `page_number` with no chunker changes.
- [ ] **Back-matter handling** — strip the index and uploader-inserted pages. Decide per book whether glossaries and answer keys are dropped or kept as separately tagged documents. Use the locations the audit recorded.
- [ ] **Maths** — pick an approach based on what the pilot finds (keep MathML as LaTeX, keep PDF glyph text, or accept loss and flag the book). Nothing speculative. First data point: Springer EPUBs put LaTeX in equation images' `alt` text, so the EPUB extractor should emit `$…$` / `$$…$$` from `alt` instead of an image link.
- [ ] **Page map from a sibling PDF** — when the chosen EPUB has no page-list but the same edition's PDF has printed page numbers (the audit reports this as a caveat), align EPUB text to PDF pages (e.g. matching section headings or distinctive sentences) and emit `<!-- page_number: N -->` markers in printed page numbers. *Machine Learning for Text* needs this.
- [ ] **Figures** — keep captions in the text. Transcribing figure images through a VLM is a later, opt-in step (ask first: it's GPU/API-heavy).
- [ ] **DjVu** — only if the pilot turns up a book that exists solely as DjVu: convert it to PDF outside the pipeline, or add an extractor.
- [ ] **Textbook cleanup rules** — regexes for running heads, page furniture and watermarks seen in the pilot books (the existing "regex/images" item).

---

## Path T3: 🧩 Textbook Chunking & Evaluation

- [ ] **Chunking strategy for textbooks** — section-aware splitting on the real heading hierarchy. Keep definitions, worked examples, callout boxes and tables whole. Split end-of-chapter exercises into their own chunks, tagged as exercises, so they don't crowd out explanatory text in retrieval.
- [ ] **Richer chunk metadata** — book, edition, chapter, section and page, taken from the manifest and the extractor, so citations read like "Book, 3rd ed., ch. 4 §4.2, p. 112".
- [ ] **Extraction fidelity check** — spot-check extracted text against the source pages (the existing "verification of information" item): sample pages per book, compare, and record the error rate in the manifest.
- [ ] **Textbook golden Q&A set** — 30–50 question → (book, page/section) pairs written by the user from the pilot books, for `eval_golden.py`. As with the RPG set, don't generate the answers from the index itself.

---

## Path 2: 🔍 Retrieval Quality (RAG Performance)

> Sequence every item here against a golden Q&A set — the textbook one from Path T3 now, rather than the RPG set in Path 1.5 — and don't build any of this speculatively. Hybrid search and reranking are likely to matter for textbooks too (technical terms, symbols, named theorems).

### Search Quality
- [ ] **Hybrid search** — combine vector similarity with BM25 keyword search. Likely the single biggest win for this corpus: RPG sourcebooks are dense with proper nouns (clan names, disciplines, NPCs, locations) that embeddings alone tend to fuzz over.
- [ ] **Cross-encoder reranking** — add a reranker (e.g., `cross-encoder/ms-marco-MiniLM`) after initial retrieval.
- [ ] **Chunk overlap tuning** — experiment with overlapping windows for better context continuity.
- [x] **Drop empty/near-empty chunks before embedding** — done as part of Path 1.5 (see there); turned out to crash indexing outright rather than merely waste an embed call. Still open: *near*-empty chunks (a few words, mostly whitespace) aren't filtered, just fully-empty ones — revisit if those turn out to be noisy in practice.
- [x] **ChromaDB collection uses L2 distance, not cosine** — found in the 2026-09-16 live check. `ChromaDBStore` called `get_or_create_collection(name=...)` without `metadata={"hnsw:space": "cosine"}`, so scores were raw L2 distances (~177–380 observed), while `QdrantStore` uses cosine. `get_or_create_collection` now passes `metadata={"hnsw:space": "cosine"}` (`src/index/vectorstores.py`). Fixed 2026-09-16, but this only takes effect on collection creation: the existing `text_corpus` collection (31 docs, 15,691 chunks) still has L2 distance until it's dropped and re-indexed (~18 min from the 2026-09-16 run) — hasn't been done yet, needs the user to confirm before re-running `main.py` over the whole corpus. Compare both with the golden set once it exists.
- [x] **Section metadata picks the outermost header** — `MarkdownChunker` preferred `Header 1` over `Header 2`/`Header 3`, and pymupdf4llm turns running page headers into H1s. Most *V5 Core Rules* chunks from pages 69–219 were therefore labelled `kindred _society_`, which tells the reader and the LLM nothing. `_consume_page_markers`'s caller now checks `Header 3` before `Header 2` before `Header 1` (`src/index/chunkers.py`). Fixed 2026-09-16. Needs re-indexing to take effect on already-indexed books (same re-index as the distance-metric fix above). Still open: dropping headers that repeat on most pages of a book — that needs corpus-wide frequency analysis, not just a per-chunk ordering fix; left for a later pass if it's still noisy after re-indexing.
- [ ] **Relevance cutoff before generation** — off-corpus questions sit clearly further away than on-topic ones: "capital of France" had a best distance of 342, against 178–210 for real questions. A `chat.max_distance` that skips the LLM when nothing is close enough would stop the grounding failure noted under Path 5. Calibrate the cutoff on the golden set, not on four questions.

### Semantic Deduplication
- [x] **Locality-Sensitive Hashing (LSH/MinHash)** — 2026-09-16: implemented as `src/dedup/family.py` (`shingle`/`minhash_signature`/`estimate_jaccard`/`cluster_families`, MinHash via `mmh3` - already an incidental transitive dependency, now declared explicitly in `requirements.txt`) plus a new root script, `find_document_families.py`. Deliberately brute-force pairwise comparison rather than LSH banding: the corpus is ~44 files (~950 pairs), so banding would be premature infrastructure at this scale - noted as a future upgrade path if the corpus grows by orders of magnitude. Dry-run by default (`python find_document_families.py config/<profile>.yaml`), reads every `.md` in `io.directories.output`, reports families above `pipeline.family_clustering.threshold` (default 0.95, matching this item's ">95%"). Live-checked against the real `text_corpus` output (31 docs, 2026-09-16): 0 families at 0.95 (the 4 byte-identical *Eberron Campaign Guide* copies are already gone via the existing exact-hash dedup, so nothing near-duplicate remains at that threshold), but at a deliberately loose 0.02 the tool correctly picks up the shared boilerplate across the 10-part "Across Eberron" AE01 series without falsely calling them duplicates at the real threshold - a reasonable sanity check that the mechanism itself works, even though this corpus currently has no real near-duplicate problem for it to solve.
- [x] **Vector DB cosine similarity check** — 2026-09-16: `IndexingPipeline._drop_near_duplicate_chunks` (`src/index/pipeline.py`), gated by new `indexing.chunk_dedup.enabled` (default `false`) and `indexing.chunk_dedup.threshold` (default 0.99, matching this item's "99%"). Before upsert, each new chunk is searched (`top_k=1`) against the store; a hit from a **different** file scoring at/above threshold gets the new chunk dropped (same-file hits are never dropped - re-indexing a file's own chunk is the existing idempotent overwrite via its deterministic ID, not a duplicate). Metric-direction logic lives in a new `BaseVectorStore.is_duplicate_score()`, implemented per store (`src/index/vectorstores.py`), consistent with the `score_note` pattern from the ChromaDB-distance-caption fix. **Left disabled everywhere, including every tracked config**: it's only meaningful against a cosine-space ChromaDB collection, and the live `text_corpus` collection is still L2 pending the re-index already tracked above - enabling it today would compare incomparable distance/similarity numbers. Covered by `tests/test_chunk_dedup.py` against a fresh (cosine) collection only.

### Document Family & Version Clustering
- [x] **Family identification pass** — 2026-09-16: uses the same MinHash clustering as the semantic-dedup item above rather than a separate name/size-similarity system (TODO's own wording allows LSH for family clustering too, and building two overlapping near-duplicate mechanisms wasn't worth it). `find_document_families.py`'s report table picks a canonical member per family via `pick_canonical` (`src/dedup/family.py`) - default heuristic: longest extracted content wins, as a proxy for "most complete version"; it's a labeled suggestion in the report, not a silent decision.
- [x] **Routing strategy** — 2026-09-16: both implemented in `find_document_families.py`, selected explicitly per invocation via `--apply --routing {supersession,temporal}` (no code-level default, since this is a real content decision best made deliberately each time rather than baked in):
  - A (Supersession) — `apply_supersession` moves every non-canonical family member's `.md` out of `io.directories.output` into a sibling `superseded/` directory (a move, not a delete - reversible). Both pipelines only ever look at what's actually in `output`, so this alone is enough to exclude superseded files from indexing without touching either pipeline's code. Known limitation, not solved here: a future full `IngestionPipeline` run would see the raw source file's `.md` missing from `output` and re-extract it from scratch - wasted work, not incorrect.
  - B (Temporal Indexing) — `apply_temporal` rewrites every family member's frontmatter to add `family_id` (uuid5 of the canonical filename) and `family_role` (`canonical`/`variant`), using the exact frontmatter format `IngestionPipeline._save_document` already writes. These flow into indexing for free: existing frontmatter → `Document.metadata` → `MarkdownChunker`'s `combined_meta` → `Chunk.metadata` → stored vector metadata pass-through needed zero changes.
  - Neither mode has been run with `--apply` against the real corpus - `find_document_families.py` currently reports 0 families on it at the default threshold, so there's nothing to route yet.

### Evaluation
- [ ] **Extend the Path 1.5 golden Q&A set** as retrieval changes land — recall/precision deltas per change, not just a one-time baseline.

---

## Path 5: 🎮 Query Interface / RAG Application

> Builds on Path 1.5's `query.py`. Bumped ahead of source-expansion and performance work — a chat interface is what actually makes retrieval-quality decisions visible to a human instead of a recall percentage.

### MVP Chat Interface
- [x] **Build chat frontend** — `app.py` (repo root), Streamlit: `streamlit run app.py -- config/<profile>.yaml`. Chat history lives in `st.session_state` for display only. Retrieval reuses `query.py`'s path (`IndexingPipeline.initialize` builds the embedder + vector store, cached with `st.cache_resource`). All async work runs on one long-lived background event loop (`src/chat/async_bridge.py`): cached `ollama.AsyncClient`s keep connections bound to their first loop, so a fresh `asyncio.run()` per Streamlit rerun fails with "Event loop is closed" on the second question. Reproduced against a stub HTTP server and covered by `tests/test_async_bridge.py`. Config problems and an unreachable Ollama/store show up as `st.error`, not a stack trace. Verified live 2026-09-16 against `text_corpus` with `llama3`, driving `app.py` through Streamlit's `AppTest`. Two questions in a row ran on the cached answerer, about 3 s each with the model warm, citations and the chunks expander both rendered, and there were no errors.
- [x] **Conversational RAG** — `src/chat/rag.py`: `RagAnswerer` embeds the question, takes the top `chat.top_k` chunks and streams an Ollama chat answer (`chat.model`, default `llama3`; `chat.temperature`, default 0.1) from a prompt of numbered context blocks. The prompt says to use only that context, cite `[n]`, and say plainly when the context doesn't cover the question. Empty retrieval skips the LLM call. Each question is answered independently (no session memory, see below). Covered by `tests/test_chat_rag.py`.
- [x] **Source citation** — each context block is labelled with file, page (`page unknown` when the chunk has none) and section, and the model is told to cite `[n]`. Under every answer, an expander lists the retrieved chunks by rank with file, page, section, raw store score and full text, so a retrieval miss can be told apart from a bad generation. Citations aren't validated: nothing checks that a `[n]` exists or supports the claim.

### Known issues from the live check (2026-09-16)
- [ ] **llama3 breaks the grounding rule on off-corpus questions.** Asked "What is the capital of France?", it said the passages don't state it, then "inferred" Paris and cited two VTM chunks that mention Paris as a Camarilla city. On-corpus answers (Brujah bane, dragonmarks, Five Nations) were faithful to their chunks. Fix with the Path 2 relevance cutoff first, then tighten the prompt; an 8B model won't follow instructions perfectly.
- [x] **No timeout on Ollama calls** — if Ollama silently stopped responding, the page hung instead of showing `st.error`, because `ollama.AsyncClient()` defaults to no timeout at all. `OllamaChatGenerator` and `OllamaEmbedder` now pass `timeout=` through to `AsyncClient` (new `ChatSettings.timeout` field, default 60s, for chat; `OllamaEmbedder` reads `timeout` from its `params` dict, same 60s default). A stall now raises inside the existing `except Exception` handlers in `app.py`'s `ask()` instead of hanging the page. Fixed 2026-09-16, not yet re-verified against a real stalled Ollama (only against the existing test suite, which mocks the client).
- [x] **Score caption is ChromaDB-specific** — `app.py` said "lower is closer" unconditionally, which is backwards for `QdrantStore` (cosine similarity, higher is closer). Added `BaseVectorStore.score_note` (`src/core/interfaces.py`), overridden per store (`src/index/vectorstores.py`), and `app.py` now renders `answerer.vectorstore.score_note` instead of a hardcoded string. Fixed 2026-09-16.

### Enhanced Features
- [ ] **Session memory** — maintain conversation history for multi-turn RPG Q&A.
- [ ] **GM tools** — NPC generator, encounter builder, lore lookup powered by the vector store.

---

## Cleaning Capabilities (Cross-Cutting)

### Dynamic Copyright & Watermark Stripper
- [ ] **`DynamicLLMCleaner` exists but is never invoked from `IngestionPipeline`** — `pipeline.dynamic_cleaner` is parsed into `PipelineSettings` but nothing reads it. Wire it in (as an optional step after the static `DocumentCleaner`) or remove the dead code — currently it's neither used nor tested end-to-end.

### Multi-Language Support
- [ ] **Language detection** — add detection capabilities for non-English documents. Not currently needed by the VTM/Eberron corpus; revisit only if a non-English source is actually added (see Path 4).
- [ ] **Non-Latin character support** — ensure extraction handles non-Latin character sets.
- [ ] **Multilingual embeddings** — upgrade to models like `multilingual-e5` for cross-language semantic search.

---

# Parked

## Path 3: 📷 OCR the Scanned RPG Corpus (parked)

> Parked 2026-09-19 with the textbook pivot. Scanned textbooks that turn up in the T1 audit go through Path T2 instead, though the Marker notes below still apply to them.
>
> The 10 VTM "(revised)" clanbooks (measured 2026-09-15: `Brujah`, `Toreador`, `Tremere`, `Nosferatu`, `Malkavian`, `Ravnos`, `Lasombra`, `Assamite`, `Followers of Set`, `Giovanni`) are image-only scans and need real OCR — `Gangrel (revised)` has a text layer already (likely embedded OCR of unknown quality; verify before trusting it as-is). Sequence this after Path 1.5 proves the pipeline works end-to-end on the easy 34 books, and after golden-Q&A results say whether OCR quality is actually the bottleneck for these books' content.

- [ ] **Re-verify Marker on the current `transformers` version** — the last confirmed-working Marker run (`Toreador`, 2026-09-12) predates the `transformers` 4.57.6 bump (2026-09-14). Smoke-test one short scanned PDF before trusting a full-book run.
- [ ] **One book at a time, `batch_size` 1–2, nothing else on the GPU** (see `CLAUDE.md` hardware limits) — do not run all 10 in one pass.
- [ ] **Table-aware chunking** — keep stat blocks and tables intact rather than splitting mid-row (matters more once these books are actually indexed).
- [ ] **Fix or drop the Gemini async-batch path** (Path 1 bug) if free-tier batching turns out to be worth it over local Marker/Surya for this remaining set — 10 books is small enough that local OCR may just be simpler.

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

# Completed foundation

> Paths 1 and 1.5 are done apart from the parked RPG golden set. Kept for the reasoning and the fix history.

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
- [ ] **A golden Q&A set (30–50 questions)** — *(RPG corpus; parked with the 2026-09-19 pivot, and Path T3 has the textbook equivalent. Left open because the harness and candidates remain usable if the RPG corpus is revisited.)* the harness exists (`eval_golden.py`, repo root, covered by `tests/test_eval_golden.py`) and reports top-k recall against `eval/golden_qa.yaml`, but the actual questions don't: `eval/golden_qa.example.yaml` ships with placeholder entries only, deliberately not filled in with fabricated answers. **Needs a human who actually knows the VTM/Eberron content** to write 30–50 real question → (source file, page) pairs. `eval/golden_qa.yaml` now exists as an empty copy of the example, ready to receive verified entries. 2026-09-16: `eval/golden_qa.candidates.yaml` adds 24 candidate questions (VTM clan weaknesses/disciplines, Eberron geography/lore) whose `expected_source`/`expected_page` came from querying the *current* index (top-1 hit), not from reading the books - explicitly not valid `eval_golden.py` input, since grading a retriever against its own output proves nothing. Three are flagged `SUSPICIOUS` (Toreador/Ravnos/Assamite questions all resolved to `Gangrel (revised).md`, the only revised clanbook with a text layer, since the real books are unindexed scans - Path 3) and should likely be discarded rather than verified. Still needs a human to check each candidate against the real PDF page and copy confirmed ones into `golden_qa.yaml`, plus write ~10-25 more to reach 30-50. This becomes the yardstick for every Path 2/3 decision below — nothing there should be started until this exists.
- [x] **Pilot run against real content** — 2026-09-15: ran `config/config_pilot.yaml` (5 hand-picked text-layer PDFs - 3 VTM, 2 Eberron, 1 to 45 pages each - plus `Toreador (revised).md`, an already-extracted file left over from an earlier session, which `IndexingPipeline.process_directory` picks up automatically since it indexes everything in the output directory) end to end: extract → clean → chunk → embed → upsert, 883 chunks total, all via `AutoPdfExtractor`'s fast text-layer path (never touched Marker). Verified retrieval qualitatively with `query.py` against both collections (VTM: "weakness of the Ahrimanes bloodline" correctly surfaced `Ahrimanes.md` p.23-27; Eberron: a Sharn/Convergence Manifesto question correctly surfaced the right Eberron file) - this is a spot-check, not the golden-Q&A recall measurement above, which still needs real questions.
- [x] **Run against the rest of the text-layer corpus** — 2026-09-16: `config/config_corpus_text.yaml` lists the 33 PDFs that pass the 100 chars/page density check explicitly, so no scan can reach Marker. Its OCR extractor name is deliberately unregistered, so a misrouted file would error instead of loading Marker. One more scan turned up: `eberron/Eberron Campaign Setting.pdf` reads 0 chars/page, making 11 scans, not 10. Dedup dropped the 3 duplicate *Eberron Campaign Guide* copies. Result: 25 newly extracted PDFs, all on CPU, no failures, in 17m46s. ChromaDB `text_corpus` holds 31 documents and 15,691 chunks, and the per-file upsert counts in the log sum to exactly that, so there are no duplicates.
