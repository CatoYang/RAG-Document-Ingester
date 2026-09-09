---
name: create-document-parser
description: >-
  Use this skill when the user asks to create a new document parser or extractor for the RAG Document Ingester project.
---

# Create Document Parser

When requested to create a new document parser, follow these steps:

## Requirements
- Ensure the parser inherits from the `BaseExtractor` interface.
- Implement the extraction logic to process the specific document type.
- All file I/O must be asynchronous (e.g., using `aiofiles`).
- All return types must be fully typed.
- Extracted text chunks must be returned as Pydantic models containing `source_metadata`.

## Steps
1. Create the new parser class in the appropriate directory (e.g., `extractors/`).
2. Define the Pydantic model for the chunk if not already available.
3. Write asynchronous methods for reading and processing the file.
4. Ensure the parser adheres to SOLID principles as defined in `AGENTS.md`.
