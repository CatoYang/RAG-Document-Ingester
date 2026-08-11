import docx
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()

class DocxExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts Word Documents with advanced comment/track-changes handling."""
    
    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        console.print(f"[cyan]Extracting Word Document {file_path_obj.name}...[/cyan]")
        
        strip_comments = self.params.get('strip_comments', True)
        
        try:
            doc = docx.Document(file_path)
        except Exception as e:
            console.print(f"[red]Error reading docx {file_path_obj.name}: {e}[/red]")
            return Document(source_file=file_path_obj.name, content="", metadata={"error": str(e)})

        markdown_content = []

        # python-docx inherently ignores comments in paragraph text.
        # Track-changes (deletions) are also typically excluded from .text, but insertions are included.
        # This gives us a naturally "clean" output without extra XML wrangling.
        
        for element in doc.element.body:
            if element.tag.endswith('p'):
                # It's a paragraph
                for p in doc.paragraphs:
                    if p._element == element:
                        text = p.text.strip()
                        if text:
                            # Basic bold/italic support could be added here by iterating runs,
                            # but for robust RAG, clean text is often enough.
                            markdown_content.append(text)
                        break
            elif element.tag.endswith('tbl'):
                # It's a table
                for t in doc.tables:
                    if t._element == element:
                        markdown_content.append("\n")
                        for i, row in enumerate(t.rows):
                            row_data = [cell.text.replace('\n', ' ').strip() for cell in row.cells]
                            markdown_content.append("| " + " | ".join(row_data) + " |")
                            if i == 0:
                                markdown_content.append("|" + "|".join(["---"] * len(row.cells)) + "|")
                        markdown_content.append("\n")
                        break

        content = "\n\n".join(markdown_content)

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "python-docx",
                "mode": "docx",
                "params": self.params
            }
        }
        
        return Document(
            source_file=file_path_obj.name,
            content=content,
            metadata=metadata
        )
