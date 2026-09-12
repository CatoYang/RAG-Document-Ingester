# Agent Architectural Rules

When operating in this directory and its subdirectories, you MUST adhere to the following strict architectural rules:

1. **Asynchronous I/O:** All file reading and I/O operations MUST be performed asynchronously (e.g., using `aiofiles` or `asyncio`). Synchronous file reads are strictly prohibited to prevent blocking the event loop.
2. **Strict Typing:** All Python code MUST use strict type hinting (e.g., using the `typing` module or modern built-in types).
3. **Pydantic Models for Chunks:** All text chunks extracted by parsers MUST be returned as Pydantic models. These models MUST contain source metadata (such as filename, page number, and chunk index).

## Environment Execution Rules

1. **WSL Ubuntu Execution:** The primary execution environment for this project is Ubuntu via WSL. Because agents operate from a Windows host context, **all pipeline commands and python scripts MUST be executed through WSL**. 
   - Never run `python ...` directly in the Windows PowerShell.
   - Always route commands into WSL using the format: `wsl --cd "/home/cato/RAG Document Ingester" python ...` or `wsl bash -c "..."`

## Architectural Rules

You MUST adhere to SOLID principles for all architectural designs and code modifications:

1. **Single Responsibility Principle (SRP):** Each class, function, or module should have one and only one reason to change. Keep extractors tightly scoped to a single document type.
2. **Open-Closed Principle (OCP):** Software entities should be open for extension, but closed for modification. If a new document type needs to be ingested, create a new Extractor class that inherits from `BaseExtractor` rather than modifying existing extractors.
3. **Liskov Substitution Principle (LSP):** Subtypes must be substitutable for their base types. All Extractors must perfectly implement the `BaseExtractor` interface and return a valid `Document` object.
4. **Interface Segregation Principle (ISP):** Keep interfaces small and focused. Do not force classes to implement methods they do not use.
5. **Dependency Inversion Principle (DIP):** High-level modules should not depend on low-level modules; both should depend on abstractions. For example, `IngestionPipeline` should depend on the `BaseExtractor` interface, not the concrete `PyMuPDFExtractor`.

When the USER requests new features, ensure your proposed Implementation Plan explicitly mentions how it respects these principles.
