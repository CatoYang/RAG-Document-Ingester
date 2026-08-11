import os
import yaml
from pathlib import Path
from rich.console import Console

from src.core.interfaces import Document
from src.indexing.registry import get_chunker_class, get_embedder_class, get_vectorstore_class

console = Console()

class IndexingPipeline:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        indexing_config = self.config.get('indexing', {})
        
        chunker_cfg = indexing_config.get('chunker', {})
        embedder_cfg = indexing_config.get('embedder', {})
        vectorstore_cfg = indexing_config.get('vectorstore', {})
        
        # Instantiate Chunker
        chunker_cls = get_chunker_class(chunker_cfg.get('type', 'MarkdownChunker'))
        self.chunker = chunker_cls(**chunker_cfg.get('params', {}))
        
        # Instantiate Embedder
        embedder_cls = get_embedder_class(embedder_cfg.get('type', 'OllamaEmbedder'))
        self.embedder = embedder_cls(**embedder_cfg.get('params', {}))
        
        # Instantiate VectorStore
        vectorstore_cls = get_vectorstore_class(vectorstore_cfg.get('type', 'ChromaDBStore'))
        self.vectorstore = vectorstore_cls(**vectorstore_cfg.get('params', {}))

    def parse_document(self, file_path: str) -> Document:
        """Parses a cleaned markdown file back into a Document object."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
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

    def process_directory(self, directory: str):
        console.print(f"[bold green]Starting Indexing Pipeline on {directory}[/bold green]")
        
        for filename in os.listdir(directory):
            if not filename.endswith('.md'):
                continue
                
            file_path = os.path.join(directory, filename)
            
            try:
                # 1. Parse file
                doc = self.parse_document(file_path)
                
                # 2. Chunk
                chunks = self.chunker.chunk(doc)
                if not chunks:
                    console.print(f"[yellow]Warning: No chunks generated for {filename}[/yellow]")
                    continue
                    
                # 3. Embed
                texts_to_embed = [c.text for c in chunks]
                embeddings = self.embedder.embed(texts_to_embed)
                
                # 4. Upsert
                self.vectorstore.upsert(chunks, embeddings)
                
                console.print(f"[bold blue]Successfully indexed {filename} ({len(chunks)} chunks)[/bold blue]")
                
            except Exception as e:
                console.print(f"[bold red]Failed to index {filename}: {e}[/bold red]")
