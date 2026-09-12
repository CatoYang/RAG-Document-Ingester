import os
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()

class PdfExtractor(BaseExtractor):
    """
    Universal PDF Extractor using Marker.
    Runs Layout Analysis, OCR, and extracts cropped images.
    Returns the base markdown ready for VLM Enrichment.
    """
    def __init__(self, **kwargs):
        self.batch_size = kwargs.get("batch_size", 4)
        
        try:
            # We delay import so the pipeline doesn't crash if marker isn't installed
            from marker.models import load_all_models
            self.model_lst = load_all_models()
        except ImportError:
            console.print("[bold red]Marker is not installed. Please run: pip install marker-pdf==0.3.10[/bold red]")
            self.model_lst = None

    def extract(self, file_path: str, **kwargs) -> Document:
        if not self.model_lst:
            raise RuntimeError("Marker is not installed.")
            
        pdf_path_obj = Path(file_path)
        output_dir_str = kwargs.get("output_dir", "data/staging/staging_markdown")
        output_dir = Path(output_dir_str)

        # Storage for images
        assets_base_dir = output_dir.parent / "assets"
        doc_asset_dir = assets_base_dir / pdf_path_obj.stem
        doc_asset_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"[cyan]Running Marker Engine on {pdf_path_obj.name}...[/cyan]")
        
        # Marker processing (0.3.10 API)
        from marker.convert import convert_single_pdf
        text, images, out_meta = convert_single_pdf(
            str(pdf_path_obj),
            self.model_lst,
            max_pages=None,
            langs=None,
            batch_multiplier=self.batch_size
        )
        
        # Save images and replace paths in markdown
        images_processed = 0
        if images:
            for filename, image in images.items():
                img_path = doc_asset_dir / filename
                image.save(str(img_path))
                
                # We format the markdown link universally: ![image](assets/doc_name/filename.png)
                try:
                    rel_to_md = os.path.relpath(img_path, output_dir).replace("\\", "/")
                except ValueError:
                    rel_to_md = str(img_path.resolve()).replace("\\", "/")
                    
                # Marker usually embeds them as ![Image](filename) or similar. 
                # We replace the raw filename with the relative path.
                text = text.replace(f"({filename})", f"({rel_to_md})")
                images_processed += 1
                
        metadata = {
            "source": pdf_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "PdfExtractor (Marker 0.3.10)",
                "images_extracted": images_processed,
                "marker_meta": out_meta
            }
        }
        
        console.print(f"[green]Marker extraction complete: {images_processed} images saved to {doc_asset_dir}[/green]")
        
        return Document(
            source_file=pdf_path_obj.name,
            content=text,
            metadata=metadata
        )
