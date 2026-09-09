import os
import yaml
import asyncio
import aiofiles
from pathlib import Path
from rich.console import Console

from src.core.interfaces import Document
from src.indexing.registry import get_chunker_class, get_embedder_class, get_vectorstore_class

console = Console()

class IndexingPipeline:
    def __init__(self):
        self.config = {}
        self.chunker = None
        self.embedder = None
        self.vectorstore = None

    async def initialize(self, config_path: str = "config/config.yaml"):
        path = Path(config_path)
        if not path.is_absolute() and not path.exists():
            project_root = Path(__file__).resolve().parent.parent.parent
            path = project_root / path
            
        async with aiofiles.open(path, 'r') as f:
            content = await f.read()
            self.config = yaml.safe_load(content)
            
        indexing_config = self.config.get('indexing', {})
        
        chunker_cfg = indexing_config.get('chunker', {})
        embedder_cfg = indexing_config.get('embedder', {})
        vectorstore_cfg = indexing_config.get('vectorstore', {})
        
        chunker_cls = get_chunker_class(chunker_cfg.get('type', 'MarkdownChunker'))
        self.chunker = chunker_cls(**chunker_cfg.get('params', {}))
        
        embedder_cls = get_embedder_class(embedder_cfg.get('type', 'OllamaEmbedder'))
        self.embedder = embedder_cls(**embedder_cfg.get('params', {}))
        
        # Instantiate VectorStore
        vectorstore_cls = get_vectorstore_class(vectorstore_cfg.get('type', 'ChromaDBStore'))
        self.vectorstore = vectorstore_cls(**vectorstore_cfg.get('params', {}))
        
        # Instantiate SummarisationPipeline
        from src.summarisation.pipeline import SummarisationPipeline
        self.summarisation = SummarisationPipeline()
        await self.summarisation.initialize(config_path)

    async def parse_document(self, file_path: str) -> Document:
        """Parses a cleaned markdown file back into a Document object asynchronously."""
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            
        # Extract YAML frontmatter if it exists
        metadata = {"source": Path(file_path).name}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    metadata.update(yaml.safe_load(parts[1]) or {})
                    content = parts[2].strip()
                except yaml.YAMLError:
                    pass
                    
        return Document(source_file=Path(file_path).name, content=content, metadata=metadata)

    async def process_file(self, file_path: str):
        filename = Path(file_path).name
        try:
            # 1. Parse file
            doc = await self.parse_document(file_path)
            
            # 2. Chunk
            chunks = await self.chunker.chunk(doc)
            if not chunks:
                console.print(f"[yellow]Warning: No chunks generated for {filename}[/yellow]")
                return
                
            # 3. Summarise (Hierarchical Indexing)
            doc_summary = await self.summarisation.generate_document_summary(doc)
            section_summaries = await self.summarisation.generate_section_summaries(chunks, doc_summary)
            
            # Embed doc summary
            if doc_summary:
                from src.core.interfaces import Chunk, SourceMetadata
                doc_meta = SourceMetadata(filename=doc.source_file, chunk_index=-1)
                doc_chunk = Chunk(text=doc_summary, source_metadata=doc_meta, metadata={"level": "document", "source": filename})
                doc_embedding = await self.embedder.embed([doc_summary])
                await self.vectorstore.upsert([doc_chunk], doc_embedding)
                
            # Embed section summaries
            if section_summaries:
                from src.core.interfaces import Chunk, SourceMetadata
                sec_chunks = []
                for sec, summary in section_summaries.items():
                    sec_meta = SourceMetadata(filename=doc.source_file, chunk_index=-2, section=sec)
                    sec_chunks.append(Chunk(text=summary, source_metadata=sec_meta, metadata={"level": "section", "source": filename}))
                sec_embeddings = await self.embedder.embed([c.text for c in sec_chunks])
                await self.vectorstore.upsert(sec_chunks, sec_embeddings)
                
            # 4. Embed raw chunks
            texts_to_embed = [c.text for c in chunks]
            embeddings = await self.embedder.embed(texts_to_embed)
            
            # 5. Upsert raw chunks
            await self.vectorstore.upsert(chunks, embeddings)
            
            console.print(f"[bold blue]Successfully indexed {filename} ({len(chunks)} chunks, hierarchical summaries: {self.summarisation.enabled})[/bold blue]")
            
        except Exception as e:
            console.print(f"[bold red]Failed to index {filename}: {e}[/bold red]")

    async def process_directory(self, directory: str):
        dir_path = Path(directory)
        if not dir_path.is_absolute():
            project_root = Path(__file__).resolve().parent.parent.parent
            dir_path = project_root / dir_path
            
        console.print(f"[bold green]Starting Indexing Pipeline on {dir_path}[/bold green]")
        
        if not dir_path.exists():
            console.print(f"[bold red]Directory {dir_path} does not exist.[/bold red]")
            return
            
        tasks = []
        for filename in os.listdir(dir_path):
            if not filename.endswith('.md'):
                continue
                
            file_path = dir_path / filename
            tasks.append(self.process_file(str(file_path)))
            
        if tasks:
            await asyncio.gather(*tasks)

if __name__ == "__main__":
    async def main():
        pipeline = IndexingPipeline()
        await pipeline.initialize()
        await pipeline.process_directory(pipeline.config.get("pipeline", {}).get("output_dir", "data/staging_markdown"))
        
    asyncio.run(main())
