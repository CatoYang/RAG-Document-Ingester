import zipfile
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()


class ArchiveUnpacker(BaseExtractor):
    """Special Extractor: Unpacks archives into a designated subfolder."""

    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        console.print(
            f"[cyan]Unpacking Archive {file_path_obj.name}...[/cyan]")

        # Determine output directory, default to a subfolder named after the archive in the same dir
        # In a fully integrated pipeline, the router should pass the
        # pipeline.output_dir via kwargs
        output_base = kwargs.get('output_dir', str(file_path_obj.parent))
        target_dir = Path(output_base) / f"{file_path_obj.stem}_unpacked"

        extracted_files = []
        if file_path_obj.suffix.lower() == '.zip':
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
                extracted_files = zip_ref.namelist()

        # Future: Handle .eml using Python's email package

        content = f"# Archive Extracted\n\nExtracted {len(extracted_files)} files to `{target_dir}`:\n"
        for f in extracted_files:
            content += f"- {f}\n"

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(
                microsecond=0).isoformat(' '),
            "extractor": {
                "program": "archive_unpacker",
                "mode": "archive"},
            "unpacked_dir": str(target_dir),
            "files_unpacked": len(extracted_files)}

        return Document(
            source_file=file_path_obj.name,
            content=content,
            metadata=metadata
        )
