import zipfile
import docx
from pathlib import Path
from datetime import datetime
from rich.console import Console
import shutil
import os

from src.core.interfaces import BaseExtractor, Document

console = Console()

class DocxExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts Word Documents with Image Extraction."""

    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        output_dir_str = kwargs.get("output_dir", "data/staging/staging_markdown")
        output_dir = Path(output_dir_str)
        
        assets_base_dir = output_dir.parent / "assets"
        doc_asset_dir = assets_base_dir / file_path_obj.stem
        doc_asset_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"[cyan]Extracting Word Document {file_path_obj.name}...[/cyan]")

        try:
            doc = docx.Document(file_path)
        except Exception as e:
            console.print(f"[red]Error reading docx {file_path_obj.name}: {e}[/red]")
            return Document(source_file=file_path_obj.name, content="", metadata={"error": str(e)})

        # 1. Extract physical images via ZipFile
        images_extracted = 0
        media_mapping = {} # Maps 'word/media/image1.png' to relative path
        try:
            with zipfile.ZipFile(file_path, 'r') as docx_zip:
                for item in docx_zip.namelist():
                    if item.startswith('word/media/'):
                        filename = Path(item).name
                        if not filename: continue
                        
                        img_data = docx_zip.read(item)
                        out_img_path = doc_asset_dir / filename
                        with open(out_img_path, 'wb') as f:
                            f.write(img_data)
                            
                        # Format relative path for markdown
                        try:
                            rel_to_md = os.path.relpath(out_img_path, output_dir).replace("\\", "/")
                        except ValueError:
                            rel_to_md = str(out_img_path.resolve()).replace("\\", "/")
                            
                        media_mapping[filename] = rel_to_md
                        images_extracted += 1
        except Exception as e:
            console.print(f"[yellow]Could not unzip media: {e}[/yellow]")

        # 2. Extract Text and match relationships
        # We need to map relationship IDs to filenames to inject them correctly
        rels = doc.part.rels
        rel_id_to_file = {}
        for rel_id, rel in rels.items():
            if "image" in rel.reltype:
                # rel.target_ref is usually something like 'media/image1.png'
                filename = Path(rel.target_ref).name
                rel_id_to_file[rel_id] = filename

        markdown_content = []

        for element in doc.element.body:
            if element.tag.endswith('p'):
                # Extract text
                for p in doc.paragraphs:
                    if p._element == element:
                        text = p.text.strip()
                        if text:
                            markdown_content.append(text)
                            
                        # Look for drawings/images in this paragraph
                        for run in p.runs:
                            # Search for <w:drawing> inside the run XML
                            if '<w:drawing' in run._element.xml or '<v:imagedata' in run._element.xml:
                                # Quick regex to find embed ID
                                import re
                                match = re.search(r'r:embed="([^"]+)"', run._element.xml)
                                if match:
                                    r_id = match.group(1)
                                    if r_id in rel_id_to_file:
                                        filename = rel_id_to_file[r_id]
                                        if filename in media_mapping:
                                            markdown_content.append(f"\\n![Image]({media_mapping[filename]})\\n")
                        break
            elif element.tag.endswith('tbl'):
                # It's a table
                for t in doc.tables:
                    if t._element == element:
                        markdown_content.append("\\n")
                        for i, row in enumerate(t.rows):
                            row_data = [cell.text.replace('\\n', ' ').strip() for cell in row.cells]
                            markdown_content.append("| " + " | ".join(row_data) + " |")
                            if i == 0:
                                markdown_content.append("|" + "|".join(["---"] * len(row.cells)) + "|")
                        markdown_content.append("\\n")
                        break

        content = "\\n\\n".join(markdown_content)
        
        console.print(f"[green]Extracted {images_extracted} images from {file_path_obj.name}[/green]")

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "DocxExtractor (Zip+XML)",
                "images_extracted": images_extracted,
                "params": self.params
            }
        }

        return Document(source_file=file_path_obj.name, content=content, metadata=metadata)
