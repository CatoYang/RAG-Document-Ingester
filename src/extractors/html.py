import warnings
from bs4 import BeautifulSoup
from bs4 import MarkupResemblesLocatorWarning
from markdownify import markdownify as md
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

# Suppress BeautifulSoup warnings about parsing URLs/filenames instead of markup
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

console = Console()

class HtmlExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts HTML, attempting to strip ads and navigation."""
    
    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        console.print(f"[cyan]Extracting HTML {file_path_obj.name}...[/cyan]")
        
        strict_content = self.params.get('strict_content', True)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            if strict_content:
                # Strip out noisy tags
                noisy_tags = ['nav', 'footer', 'aside', 'script', 'style', 'noscript', 'iframe', 'header']
                for tag in soup.find_all(noisy_tags):
                    tag.decompose()
            
            # Convert to markdown
            markdown_text = md(str(soup), heading_style="ATX", escape_asterisks=False, bullets="-")
            
        except Exception as e:
            console.print(f"[red]Error parsing HTML {file_path_obj.name}: {e}[/red]")
            return Document(source_file=file_path_obj.name, content="", metadata={"error": str(e)})

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "beautifulsoup_markdownify",
                "mode": "html",
                "params": self.params
            }
        }
        
        return Document(
            source_file=file_path_obj.name,
            content=markdown_text.strip(),
            metadata=metadata
        )
