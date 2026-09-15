import pytest

from src.core.interfaces import Document
from src.extract.pdf_text import PAGE_MARKER_TEMPLATE
from src.index.chunkers import MarkdownChunker


@pytest.mark.asyncio
async def test_chunker_recovers_page_numbers_from_markers():
    content = (
        "# Chapter One\n\n"
        + PAGE_MARKER_TEMPLATE.format(page=1) + "\n\n"
        + "Page one content. " * 10 + "\n\n"
        + "## Section A\n\n"
        + PAGE_MARKER_TEMPLATE.format(page=2) + "\n\n"
        + "Page two content. " * 10
    )
    doc = Document(source_file="book.pdf", content=content, metadata={})

    chunker = MarkdownChunker(chunk_size=1000, chunk_overlap=0)
    chunks = await chunker.chunk(doc)

    assert len(chunks) >= 2
    pages = [c.source_metadata.page_number for c in chunks]
    # Non-decreasing: page numbers should never go backwards across chunks.
    assert pages == sorted(pages)
    assert pages[0] == 1
    assert pages[-1] == 2
    # The marker itself must not leak into the embedded/displayed chunk text.
    assert all("page_number:" not in c.text for c in chunks)


@pytest.mark.asyncio
async def test_chunker_drops_empty_chunks():
    """An empty chunk isn't just wasted work - OllamaEmbedder returns a
    zero-length embedding for an empty prompt, which crashes ChromaDB's
    upsert (reproduced against a real Ollama host and ChromaDB, 2026-09-15,
    on content starting with a page marker and no leading header)."""
    content = (
        PAGE_MARKER_TEMPLATE.format(page=1) + "\n\n"
        + "# Chapter One\n\nReal content here."
    )
    doc = Document(source_file="book.pdf", content=content, metadata={})

    chunker = MarkdownChunker(chunk_size=1000, chunk_overlap=0)
    chunks = await chunker.chunk(doc)

    assert all(c.text for c in chunks)
    # chunk_index must stay a contiguous 0..N-1 sequence over kept chunks,
    # not a sparse index into the pre-filtering split list.
    assert [c.source_metadata.chunk_index for c in chunks] == list(range(len(chunks)))


@pytest.mark.asyncio
async def test_chunker_handles_documents_without_page_markers():
    """Documents from extractors that don't emit page markers (everything
    except PyMuPDF4LLMExtractor, for now) must still chunk fine, with
    page_number left as None rather than erroring."""
    doc = Document(source_file="notes.docx", content="# Title\n\nSome body text with no page markers at all.", metadata={})

    chunker = MarkdownChunker(chunk_size=1000, chunk_overlap=0)
    chunks = await chunker.chunk(doc)

    assert len(chunks) >= 1
    assert all(c.source_metadata.page_number is None for c in chunks)
