import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document
from src.extractors.universal import MarkItDownExtractor

console = Console()


class OpenOfficeExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts OpenOffice (.odt, .ods, .odp) to .docx using headless LibreOffice, then parses via MarkItDown."""

    def __init__(self):
        # Verify LibreOffice is installed and accessible
        if not shutil.which("libreoffice"):
            raise RuntimeError(
                "LibreOffice is not installed or not in PATH. Please run `sudo apt install libreoffice`.")

        self.markitdown_extractor = MarkItDownExtractor()

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            console.print(
                f"[cyan]Converting {file_path_obj.name} to .docx via headless LibreOffice...[/cyan]")

            # Run the headless conversion
            # Syntax: libreoffice --headless --convert-to docx <file> --outdir
            # <dir>
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
                console.print(
                    f"[bold red]LibreOffice conversion failed: {e.stderr}[/bold red]")
                raise

            # Find the converted file in the temp directory
            converted_files = list(temp_dir_path.glob("*.docx"))
            if not converted_files:
                raise FileNotFoundError(
                    f"LibreOffice succeeded but no .docx file was found in {temp_dir_path}")

            converted_file_path = converted_files[0]

            # Pass the converted file to MarkItDown
            console.print(
                f"[cyan]Extracting Markdown from converted file using MarkItDown...[/cyan]")
            # We bypass the MarkItDownExtractor's standard extract() to avoid nested Documents,
            # or we can just call it and merge metadata. Let's call it and
            # overwrite the source.
            sub_doc = self.markitdown_extractor.extract(
                str(converted_file_path))

            metadata = {
                "source": file_path_obj.name,
                "date_ingested": datetime.now().replace(
                    microsecond=0).isoformat(' '),
                "extractor": {
                    "program": "libreoffice_headless",
                    "version": "system",
                    "mode": "openoffice_conversion"}}

            return Document(
                source_file=file_path_obj.name,
                content=sub_doc.content,
                metadata=metadata
            )
