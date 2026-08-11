from pathlib import Path
from datetime import datetime
from markitdown import MarkItDown
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()

class PresentationExtractor(BaseExtractor):
    """Tier 2/3 Extractor: Converts Presentations, capturing speaker notes."""
    
    def __init__(self, **kwargs):
        self.md = MarkItDown()
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        console.print(f"[cyan]Extracting Presentation {file_path_obj.name}...[/cyan]")
        
        try:
            # MarkItDown natively parses PPTX, extracting both slide text and speaker notes.
            result = self.md.convert(file_path)
        except Exception as e:
            console.print(f"[red]Error parsing presentation {file_path_obj.name}: {e}[/red]")
            return Document(source_file=file_path_obj.name, content="", metadata={"error": str(e)})
        
        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "markitdown",
                "mode": "presentation",
                "params": self.params
            }
        }
        
        return Document(
            source_file=file_path_obj.name,
            content=result.text_content,
            metadata=metadata
        )
