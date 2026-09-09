from typing import List, Dict, Any
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from rich.console import Console

from src.core.interfaces import BaseChunker, Document, Chunk, SourceMetadata

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

    async def chunk(self, doc: Document) -> List[Chunk]:
        console.print(f"[dim]Chunking {doc.source_file}...[/dim]")
        
        # 1. Split by Markdown headers
        md_splits = self.md_splitter.split_text(doc.content)
        
        # 2. Recursively split any sections that are still too large
        splits = self.text_splitter.split_documents(md_splits)
        
        chunks = []
        for i, s in enumerate(splits):
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
                
            source_metadata = SourceMetadata(
                filename=doc.source_file,
                page_number=combined_meta.get("page_number", None),
                section=section,
                chunk_index=i
            )
            
            chunks.append(Chunk(text=s.page_content, source_metadata=source_metadata, metadata=combined_meta))
            
        return chunks
