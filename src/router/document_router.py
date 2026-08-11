from pathlib import Path
import pymupdf
from rich.console import Console

from src.core.interfaces import BaseRouter, BaseExtractor
from src.config.settings import Config
from src.extractors.registry import get_extractor_class

console = Console()

class DocumentRouter(BaseRouter):
    """Triages documents and assigns the appropriate extractor."""
    
    def __init__(self, config: Config):
        self.config = config
        
    def _check_pdf_text_density(self, file_path: str) -> float:
        """Calculates the average text density per page of a PDF."""
        try:
            doc = pymupdf.open(file_path)
            total_text_length = 0
            
            # Check up to first 5 pages for speed
            pages_to_check = min(5, len(doc))
            if pages_to_check == 0:
                return 0.0
                
            for i in range(pages_to_check):
                page = doc.load_page(i)
                text = page.get_text()
                total_text_length += len(text.strip())
                
            doc.close()
            
            # Very basic heuristic: average characters per page
            avg_chars_per_page = total_text_length / pages_to_check
            
            # If avg chars is very low, it's likely a scanned image or heavily stylized
            if avg_chars_per_page < 100:
                return 0.05
            return 1.0
            
        except Exception as e:
            console.print(f"[bold red]Error checking PDF density: {e}[/bold red]")
            return 0.0
            
    def get_extractor(self, file_path: str) -> BaseExtractor:
        """Determines the appropriate extractor based on file extension and config."""
        path = Path(file_path)
        ext = path.suffix.lower()
        
        if ext not in self.config.file_rules:
            raise ValueError(f"Unsupported file type or missing in config: {ext}")
            
        rule = self.config.file_rules[ext]
        
        try:
            extractor_cls = get_extractor_class(rule.extractor)
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
            # Fallback
            if rule.fallback:
                console.print(f"[yellow]Attempting fallback to {rule.fallback}...[/yellow]")
                extractor_cls = get_extractor_class(rule.fallback)
            else:
                raise
        
        # Instantiate extractor passing params from file_rules
        console.print(f"[green]Routing {path.name} to {extractor_cls.__name__}...[/green]")
        return extractor_cls(**rule.params)
