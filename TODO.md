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
