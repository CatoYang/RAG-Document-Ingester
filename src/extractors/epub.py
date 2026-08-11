from pathlib import Path
from datetime import datetime
from epub2txt import epub2txt
import importlib.metadata
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()

class EpubExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts EPUB e-books to Markdown text."""
    
    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        
        console.print(f"[cyan]Parsing EPUB structure for {file_path_obj.name}...[/cyan]")
        
        try:
            # Extract text from epub
            text_content = epub2txt(file_path)
        except Exception as e:
            console.print(f"[bold red]Failed to parse EPUB: {e}[/bold red]")
            raise
            
        try:
            version = importlib.metadata.version("epub2txt")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
            
        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "epub2txt",
                "version": version,
                "mode": "epub_text"
            }
        }
        
        return Document(
            source_file=file_path_obj.name,
            content=text_content,
            metadata=metadata
        )
