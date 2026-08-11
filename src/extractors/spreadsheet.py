import pandas as pd
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()

class SpreadsheetExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts Spreadsheets to structured Markdown/JSON."""
    
    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        console.print(f"[cyan]Extracting Spreadsheet {file_path_obj.name}...[/cyan]")
        
        skip_empty = self.params.get('skip_empty_sheets', True)
        
        try:
            # Load all sheets
            sheets = pd.read_excel(file_path, sheet_name=None)
        except Exception as e:
            console.print(f"[red]Error reading spreadsheet {file_path_obj.name}: {e}[/red]")
            return Document(
                source_file=file_path_obj.name,
                content="",
                metadata={"error": str(e)}
            )

        markdown_content = []
        for sheet_name, df in sheets.items():
            if skip_empty and df.empty:
                continue
            
            markdown_content.append(f"## Sheet: {sheet_name}\n")
            
            # Using tabulate behind the scenes to convert pandas to markdown
            try:
                sheet_md = df.to_markdown(index=False)
                markdown_content.append(sheet_md)
            except Exception as e:
                markdown_content.append(f"*Error formatting sheet: {e}*")
            
            markdown_content.append("\n---\n")

        content = "\n".join(markdown_content)

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "pandas",
                "mode": "spreadsheet",
                "params": self.params
            }
        }
        
        return Document(
            source_file=file_path_obj.name,
            content=content,
            metadata=metadata
        )
