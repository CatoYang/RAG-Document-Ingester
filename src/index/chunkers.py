import re
from typing import List, Optional
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from rich.console import Console

from src.core.interfaces import BaseChunker, Document, Chunk, SourceMetadata
from src.extract.pdf_text import PAGE_MARKER_PATTERN

console = Console()


class MarkdownChunker(BaseChunker):
    """Chunks documents based on Markdown headers, then recursively if needed."""

    def __init__(self, **kwargs):
        self.params = kwargs
        # Default headers to split on
        headers = self.params.get('headers_to_split_on', [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3")
        ])
        # LangChain's markdown splitter expects tuples
        headers_to_split_on = [(h[0], h[1]) for h in headers]

        self.md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False
        )

        self.chunk_size = self.params.get('chunk_size', 1000)
        self.chunk_overlap = self.params.get('chunk_overlap', 200)

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def _consume_page_markers(self, text: str, current_page: Optional[int]) -> tuple[str, Optional[int]]:
        """Strips `PAGE_MARKER_PATTERN` comments (emitted by
        PyMuPDF4LLMExtractor, one per page) out of chunk text, returning the
        cleaned text and the page number in effect by the end of this chunk.
        A chunk with no marker of its own inherits `current_page` from the
        previous chunk, since it falls between two page boundaries."""
        page_numbers = [int(m) for m in PAGE_MARKER_PATTERN.findall(text)]
        if page_numbers:
            current_page = page_numbers[-1]

        cleaned = PAGE_MARKER_PATTERN.sub('', text)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return cleaned, current_page

    async def chunk(self, doc: Document) -> List[Chunk]:
        console.print(f"[dim]Chunking {doc.source_file}...[/dim]")

        # 1. Split by Markdown headers
        md_splits = self.md_splitter.split_text(doc.content)

        # 2. Recursively split any sections that are still too large
        splits = self.text_splitter.split_documents(md_splits)

        chunks = []
        current_page: Optional[int] = None
        for s in splits:
            combined_meta = doc.metadata.copy()
            combined_meta.update(s.metadata)

            # Determine section from headers if present
            section = None
            if "Header 1" in s.metadata:
                section = s.metadata["Header 1"]
            elif "Header 2" in s.metadata:
                section = s.metadata["Header 2"]
            elif "Header 3" in s.metadata:
                section = s.metadata["Header 3"]

            text, current_page = self._consume_page_markers(s.page_content, current_page)

            if not text:
                # Splitting by header can produce an empty leading split when
                # a document's content starts before its first header (or a
                # split that was only ever a page marker). An empty chunk
                # isn't just wasted work: OllamaEmbedder returns a
                # zero-length embedding for an empty prompt, which crashes
                # ChromaDB's upsert (IndexError, not caught until far from
                # its actual cause) - so this must be filtered here, not
                # merely treated as a later "nice to have".
                continue

            page_number = combined_meta.get("page_number", current_page)

            source_metadata = SourceMetadata(
                filename=doc.source_file,
                page_number=page_number,
                section=section,
                chunk_index=len(chunks)
            )

            chunks.append(
                Chunk(
                    text=text,
                    source_metadata=source_metadata,
                    metadata=combined_meta))

        return chunks
