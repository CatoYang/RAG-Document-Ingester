# Future Considerations & Backlog

## Extractor Capabilities

### Google Drive Integration (`.gdoc`, `.gsheet`, `.gslides`)
- **Problem:** Google Workspace files synced to a local drive are merely pointer files containing web URLs, not actual data. The pipeline currently requires users to manually export these as `.docx` or `.pdf` prior to ingestion.
- **Proposed Solution:** Implement a `GoogleDriveExtractor`.
- **Implementation Notes:**
  - Requires setting up a GCP project with the Google Drive API enabled.
  - Implement OAuth 2.0 authentication to securely authorize the pipeline.
  - When the router intercepts a `.gdoc` pointer, parse the file ID from the JSON stub.
  - Use the Google Drive API to download an exported `.docx` version into a secure `tempfile.TemporaryDirectory()`.
  - Pass the downloaded file to the `MarkItDownExtractor`.
  - Ensure sensitive credentials (like `client_secret.json`) are tightly managed and excluded from version control via `.gitignore`.

## Cleaning Capabilities

### Dynamic Copyright & Watermark Stripper
- **Problem:** Copyright strings and watermarks are currently hardcoded in `config.yaml` using static regex. Over time, documents from different publishers (e.g., beyond just Hasbro or Wizards of the Coast) will have wildly different and difficult-to-strip legal boilerplates and watermarks.
- **Proposed Solution:** Implement a dynamic cleaner module that can intelligently detect and strip copyright notices and watermarks regardless of the publisher's specific wording or naming convention.

## Pipeline Capabilities

### Multi-Language Support
- **Problem:** The pipeline currently lacks dedicated functionality for processing and indexing documents in various languages.
- **Proposed Solution:** Add language detection capabilities, support for non-Latin character sets during extraction, and upgrade embedding models to multilingual variants (e.g., `multilingual-e5`) to ensure accurate semantic search across different languages.

### Diagram Handling
- **Problem:** There is currently no specialized handling for extracting information or structure from diagrams, flowcharts, or complex graphs.
- **Proposed Solution:** Integrate a specialized Vision-Language Model (VLM) or graph-extraction tool that can interpret diagrams and convert them into structured text (like Mermaid.js syntax) or detailed descriptive summaries for the RAG pipeline.

## Intelligent Curation & Deduplication

### Semantic / Fuzzy Deduplication
- **Problem:** Exact file deduplication misses documents that are virtually identical but have slight metadata differences, or paragraphs that are duplicated across different documents.
- **Proposed Solution:** 
  1. **Locality-Sensitive Hashing (LSH/MinHash):** Fast pre-computation on extracted text to drop documents that are >95% similar.
  2. **Vector DB Cosine Similarity:** Check chunks against the vector database before upserting; drop chunks if a 99% semantic match already exists.

### Document Family & Version Clustering
- **Problem:** When multiple versions of the same document exist (v1, v2, v3, FINAL), naive ingestion floods the index with conflicting information, confusing the RAG model.
- **Proposed Solution:** Implement a "Family Identification" pass prior to chunking.
  - Group files into "families" using name similarity, Locality-Sensitive Hashing, or size heuristics.
  - Implement a routing strategy to either: 
    - **A (Supersession):** Intelligently identify and keep only the latest version, discarding older drafts.
    - **B (Temporal Indexing):** Index all versions but strictly tag them with chronological/version metadata so the retrieval system can differentiate current policies from historical ones.
