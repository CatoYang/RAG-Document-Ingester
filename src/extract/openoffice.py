import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document
from src.extract.docx import DocxExtractor

console = Console()

class OpenOfficeExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts OpenOffice to .docx, then parses via DocxExtractor to extract images."""

    def __init__(self, **kwargs):
        if not shutil.which("libreoffice"):
            console.print("[yellow]LibreOffice is not installed. OpenOffice extraction may fail.[/yellow]")
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            console.print(f"[cyan]Converting {file_path_obj.name} to .docx via LibreOffice...[/cyan]")

            try:
                subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to",
                        "docx",
                        str(file_path_obj.absolute()),
                        "--outdir",
                        str(temp_dir_path.absolute())
                    ],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                console.print(f"[bold red]LibreOffice conversion failed: {e.stderr}[/bold red]")
                return Document(source_file=file_path_obj.name, content="", metadata={"error": "LibreOffice failed"})

            converted_files = list(temp_dir_path.glob("*.docx"))
            if not converted_files:
                return Document(source_file=file_path_obj.name, content="", metadata={"error": "No docx produced"})

            converted_file_path = converted_files[0]

            console.print(f"[cyan]Extracting Media and Markdown using DocxExtractor...[/cyan]")
            
            # We initialize DocxExtractor and pass the kwargs so it knows where output_dir is
            docx_extractor = DocxExtractor(**self.params)
            
            # The output assets will correctly be named after the original file because we spoof the path
            # Wait, DocxExtractor uses the path we pass to it. So if we pass a temp path, it will name the asset folder 'temp_xxxxx'.
            # We need to rename the temp file to the original file's stem + .docx
            renamed_temp_path = temp_dir_path / f"{file_path_obj.stem}.docx"
            shutil.move(str(converted_file_path), str(renamed_temp_path))
            
            sub_doc = docx_extractor.extract(str(renamed_temp_path), **kwargs)

            metadata = {
                "source": file_path_obj.name,
                "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
                "extractor": {
                    "program": "libreoffice + DocxExtractor",
                    "mode": "openoffice_conversion"
                }
            }

            return Document(source_file=file_path_obj.name, content=sub_doc.content, metadata=metadata)
