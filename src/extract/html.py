import warnings
from bs4 import BeautifulSoup
from bs4 import MarkupResemblesLocatorWarning
from markdownify import markdownify as md
from pathlib import Path
from datetime import datetime
from rich.console import Console
import base64
import urllib.request
import os
import shutil

from src.core.interfaces import BaseExtractor, Document

# Suppress BeautifulSoup warnings about parsing URLs/filenames instead of markup
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

console = Console()


class HtmlExtractor(BaseExtractor):
    """Tier 2 Extractor: Converts HTML, strips ads, and extracts/downloads images."""

    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)
        output_dir_str = kwargs.get("output_dir", "data/staging/staging_markdown")
        output_dir = Path(output_dir_str)
        
        assets_base_dir = output_dir.parent / "assets"
        doc_asset_dir = assets_base_dir / file_path_obj.stem
        doc_asset_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"[cyan]Extracting HTML {file_path_obj.name}...[/cyan]")

        strict_content = self.params.get('strict_content', True)
        images_extracted = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, 'html.parser')

            if strict_content:
                # Strip out noisy tags
                noisy_tags = ['nav', 'footer', 'aside', 'script', 'style', 'noscript', 'iframe', 'header']
                for tag in soup.find_all(noisy_tags):
                    tag.decompose()

            # Process Images
            for img in soup.find_all('img'):
                src = img.get('src')
                if not src:
                    continue
                    
                img_filename = f"image_{images_extracted}.png"
                out_img_path = doc_asset_dir / img_filename
                
                try:
                    if src.startswith('data:image'):
                        # Parse Base64
                        header, encoded = src.split(",", 1)
                        img_data = base64.b64decode(encoded)
                        with open(out_img_path, 'wb') as f:
                            f.write(img_data)
                    elif src.startswith('http'):
                        # Download web image
                        req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req) as response:
                            with open(out_img_path, 'wb') as f:
                                f.write(response.read())
                    else:
                        # Local path
                        local_path = file_path_obj.parent / src
                        if local_path.exists():
                            shutil.copy(str(local_path), str(out_img_path))
                        else:
                            continue # Skip if local file missing
                            
                    # Update the HTML tag so markdownify builds the correct link
                    try:
                        rel_to_md = os.path.relpath(out_img_path, output_dir).replace("\\\\", "/")
                    except ValueError:
                        rel_to_md = str(out_img_path.resolve()).replace("\\\\", "/")
                        
                    img['src'] = rel_to_md
                    images_extracted += 1
                    
                except Exception as e:
                    console.print(f"[yellow]Failed to extract image {src[:30]}... : {e}[/yellow]")
                    continue

            # Convert to markdown
            markdown_text = md(
                str(soup),
                heading_style="ATX",
                escape_asterisks=False,
                bullets="-"
            )
            
            console.print(f"[green]Extracted {images_extracted} images from {file_path_obj.name}[/green]")

        except Exception as e:
            console.print(f"[red]Error parsing HTML {file_path_obj.name}: {e}[/red]")
            return Document(source_file=file_path_obj.name, content="", metadata={"error": str(e)})

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "HtmlExtractor (BS4 + Markdownify)",
                "images_extracted": images_extracted,
                "params": self.params
            }
        }

        return Document(
            source_file=file_path_obj.name,
            content=markdown_text.strip(),
            metadata=metadata
        )
