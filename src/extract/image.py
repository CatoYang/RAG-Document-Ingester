import os
import shutil
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()

class ImageExtractor(BaseExtractor):
    """Tier 1 Extractor: Copies image to assets and generates markdown link for Batch API."""

    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        output_dir_str = kwargs.get("output_dir", "data/staging/staging_markdown")
        output_dir = Path(output_dir_str)
        
        assets_base_dir = output_dir.parent / "assets"
        doc_asset_dir = assets_base_dir / file_path_obj.stem
        doc_asset_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"[cyan]Queueing Image {file_path_obj.name}...[/cyan]")

        out_img_path = doc_asset_dir / file_path_obj.name
        try:
            shutil.copy(str(file_path_obj), str(out_img_path))
        except Exception as e:
            console.print(f"[red]Failed to copy image: {e}[/red]")
            return Document(source_file=file_path_obj.name, content="", metadata={"error": str(e)})

        try:
            rel_to_md = os.path.relpath(out_img_path, output_dir).replace("\\\\", "/")
        except ValueError:
            rel_to_md = str(out_img_path.resolve()).replace("\\\\", "/")

        # Output a simple markdown link
        md_text = f"![{file_path_obj.stem}]({rel_to_md})\\n"

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "ImageExtractor (Passthrough)",
                "images_extracted": 1
            }
        }

        return Document(source_file=file_path_obj.name, content=md_text, metadata=metadata)
