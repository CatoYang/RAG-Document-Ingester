import os
import subprocess
import re
from pathlib import Path
from datetime import datetime
import pymupdf
import pymupdf4llm
from PIL import Image
import ollama
import importlib.metadata
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from tenacity import retry, wait_exponential, stop_after_attempt

from src.core.interfaces import BaseExtractor, Document

console = Console()


class PdfTextExtractor(BaseExtractor):
    """Tier 1 Extractor: Uses PyMuPDF4LLM for clean, text-heavy PDFs."""

    def extract(self, file_path: str, **kwargs) -> Document:
        pdf_path_obj = Path(file_path)

        doc = pymupdf.open(file_path)
        page_count = len(doc)
        doc.close()

        with console.status(f"[cyan]Extracting {page_count} pages with PyMuPDF4LLM...[/cyan]"):
            md_text = pymupdf4llm.to_markdown(file_path)

        try:
            version = importlib.metadata.version("pymupdf4llm")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"

        metadata = {
            "source": pdf_path_obj.name,
            "page_count": page_count,
            "date_ingested": datetime.now().replace(
                microsecond=0).isoformat(' '),
            "extractor": {
                "program": "pymupdf4llm",
                "version": version,
                "mode": "pdf_text"}}

        return Document(
            source_file=pdf_path_obj.name,
            content=md_text,
            metadata=metadata
        )


class PdfVLMExtractor(BaseExtractor):
    """Tier 3 Extractor: Uses Ollama Vision Models for heavily visual PDFs."""

    def __init__(self, **kwargs):
        self.model = kwargs.get("model", "minicpm-v")
        self.dpi = kwargs.get("dpi", 300)
        self.temperature = kwargs.get("temperature", 0.0)
        self.num_ctx = kwargs.get("num_ctx", None)
        self.top_k = kwargs.get("top_k", None)
        self.top_p = kwargs.get("top_p", None)
        self.seed = kwargs.get("seed", None)
        self.client = self._get_ollama_client()
        self.prompt = (
            "You are a strict OCR (Optical Character Recognition) engine. Your only job is to extract "
            "the exact text from the provided image and format it as Markdown.\n\n"
            "Rules:\n"
            "1. TRANSCRIBE EXACTLY WHAT IS WRITTEN. Do not hallucinate, guess, or make up any text.\n"
            "2. If you cannot read a word, output [UNREADABLE].\n"
            "3. Preserve the original layout, paragraphs, headers, and lists.\n"
            "4. Do not add any conversational text, explanations, or summaries.\n\n"
            "Output ONLY the transcribed markdown.")

    def _get_ollama_client(self):
        """Returns an Ollama client, automatically adjusting for WSL2 networking."""
        host = "http://127.0.0.1:11434"
        if "WSL_DISTRO_NAME" in os.environ:
            try:
                result = subprocess.run(
                    ['ip', 'route'], capture_output=True, text=True, check=True)
                for line in result.stdout.split('\n'):
                    if line.startswith('default via'):
                        wsl_ip = line.split(' ')[2]
                        host = f"http://{wsl_ip}:11434"
                        break
            except Exception:
                pass
        return ollama.Client(host=host)

    def extract(self, file_path: str, **kwargs) -> Document:
        pdf_path_obj = Path(file_path)

        doc = pymupdf.open(file_path)
        page_count = len(doc)

        md_text = ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Extracting {page_count} pages with {self.model}...",
                total=page_count)

            for page_num in range(page_count):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=self.dpi)
                image_bytes = pix.tobytes("png")

                options = {}
                if self.temperature is not None:
                    options['temperature'] = self.temperature
                if self.num_ctx is not None:
                    options['num_ctx'] = self.num_ctx
                if self.top_k is not None:
                    options['top_k'] = self.top_k
                if self.top_p is not None:
                    options['top_p'] = self.top_p
                if self.seed is not None:
                    options['seed'] = self.seed

                response = self.client.chat(
                    model=self.model,
                    messages=[
                        {
                            'role': 'user',
                            'content': self.prompt,
                            'images': [image_bytes]
                        }
                    ],
                    options=options
                )

                page_md = response['message']['content'].strip()
                md_text += f"\n<!-- PAGE {page_num + 1} -->\n{page_md}\n"

                progress.advance(task)

        doc.close()

        try:
            version = importlib.metadata.version("ollama")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"

        metadata = {
            "source": pdf_path_obj.name,
            "page_count": page_count,
            "date_ingested": datetime.now().replace(
                microsecond=0).isoformat(' '),
            "extractor": {
                "program": "ollama",
                "version": version,
                "model": self.model,
                "mode": "pdf_vision",
                "dpi": self.dpi,
            }}
        if self.temperature is not None:
            metadata["extractor"]["temperature"] = self.temperature

        return Document(
            source_file=pdf_path_obj.name,
            content=md_text,
            metadata=metadata
        )


class HybridPdfExtractor(BaseExtractor):
    """Tier 2.5 Extractor: Fast native text via PyMuPDF4LLM + VLM OCR for large images/diagrams."""

    def __init__(self, **kwargs):
        # We default to gemini if it's in the config, or fall back to minicpm-v
        self.vlm_model = kwargs.get("vlm_model", "gemini-3.6-flash")
        self.max_image_pixels = kwargs.get('max_image_pixels', 2000000)
        self.min_image_pixels = kwargs.get(
            "min_image_pixels", 25000)  # e.g. 150x150
        self.max_image_pixels = kwargs.get("max_image_pixels", 2000000)
        self.dpi = kwargs.get("dpi", 300)
        self.temperature = kwargs.get("temperature", 0.0)
        self.prompt = (
            "You are an expert data extraction engine. Describe this image in detail. "
            "If it contains data, charts, tables, or text, transcribe them perfectly as Markdown. "
            "Do not include conversational filler.")
        self._init_vlm()

    def _init_vlm(self):
        self.use_gemini = False
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and "gemini" in self.vlm_model.lower():
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=api_key)
                self.use_gemini = True
            except Exception as e:
                console.print(f"[red]Failed to initialize Gemini: {e}[/red]")
        
        if not self.use_gemini:
            self.client = self._get_ollama_client()

    @retry(wait=wait_exponential(multiplier=2, min=4, max=60), stop=stop_after_attempt(6))
    def _get_vlm_response(self, image_bytes, img_full_path):
        if self.use_gemini:
            from google.genai import types
            response = self.gemini_client.models.generate_content(
                model=self.vlm_model,
                contents=[
                    self.prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type='image/png')
                ]
            )
            return response.text.strip()
        else:
            response = self.client.chat(
                model=self.vlm_model,
                messages=[{
                    'role': 'user',
                    'content': self.prompt,
                    'images': [image_bytes]
                }],
                options={'temperature': self.temperature}
            )
            return response['message']['content'].strip()

    def _get_ollama_client(self):
        host = "http://127.0.0.1:11434"
        if "WSL_DISTRO_NAME" in os.environ:
            try:
                result = subprocess.run(
                    ['ip', 'route'], capture_output=True, text=True, check=True)
                for line in result.stdout.split('\n'):
                    if line.startswith('default via'):
                        wsl_ip = line.split(' ')[2]
                        host = f"http://{wsl_ip}:11434"
                        break
            except Exception:
                pass
        return ollama.Client(host=host)

    def extract(self, file_path: str, **kwargs) -> Document:
        import shutil
        import tempfile
        import pymupdf

        pdf_path_obj = Path(file_path)
        output_dir_str = kwargs.get(
            "output_dir", "data/staging/staging_markdown")
        output_dir = Path(output_dir_str)

        # Create assets folder: data/staging/assets/[Document Name]
        assets_base_dir = output_dir.parent / "assets"
        doc_asset_dir = assets_base_dir / pdf_path_obj.stem
        doc_asset_dir.mkdir(parents=True, exist_ok=True)

        # Create a space-free temporary directory in the OS temp folder for
        # pymupdf4llm
        temp_img_dir = Path(tempfile.mkdtemp())

        try:
            doc = pymupdf.open(file_path)
            total_pages = len(doc)

            md_text_chunks = []
            images_processed = 0
            images_deleted = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"[cyan]Hybrid Parsing {pdf_path_obj.name} (Page-by-Page)...",
                    total=total_pages)

                for page_num in range(total_pages):
                    # 1. Extract text + images for just this ONE page (saves
                    # RAM)
                    page_md = pymupdf4llm.to_markdown(
                        doc,
                        pages=[page_num],
                        write_images=True,
                        image_path=str(temp_img_dir),
                        dpi=self.dpi)

                    # 2. Find images in this page's markdown
                    image_pattern = re.compile(r'!\[.*?\]\((.*?)\)')
                    matches = list(image_pattern.finditer(page_md))

                    for match in matches:
                        img_rel_path = match.group(1)
                        img_full_path = Path(img_rel_path)

                        # Resolve to absolute path
                        if not img_full_path.is_absolute():
                            if (temp_img_dir / img_full_path.name).exists():
                                img_full_path = temp_img_dir / img_full_path.name

                        if not img_full_path.exists():
                            continue

                        # Check dimensions
                        try:
                            with Image.open(img_full_path) as img:
                                width, height = img.size
                                pixels = width * height
                        except Exception:
                            continue

                        # Filter out tiny decor AND massive full-page parchment backgrounds
                        # Default max_image_pixels is 2,000,000 (roughly a full
                        # page at 150 DPI)
                        if pixels < self.min_image_pixels or pixels > getattr(
                                self, 'max_image_pixels', 2000000):
                            try:
                                img_full_path.unlink(missing_ok=True)
                            except BaseException:
                                pass
                            page_md = page_md.replace(match.group(0), "")
                            images_deleted += 1
                        else:
                            # Meaningful image -> VLM OCR
                            progress.update(
                                task, description=f"[cyan]OCR on Page {page_num+1} ({self.vlm_model})...")
                            try:
                                with open(img_full_path, "rb") as f:
                                    image_bytes = f.read()

                                vlm_text = self._get_vlm_response(
                                    image_bytes, img_full_path)

                                # Move image to final asset directory
                                final_img_path = doc_asset_dir / img_full_path.name
                                shutil.move(
                                    str(img_full_path), str(final_img_path))

                                # Fix the relative path to be accessible from
                                # the markdown file's location
                                try:
                                    rel_to_md = os.path.relpath(
                                        final_img_path, output_dir)
                                    rel_to_md = rel_to_md.replace("\\", "/")
                                except ValueError:
                                    rel_to_md = str(
                                        final_img_path.resolve()).replace(
                                        "\\", "/")

                                vlm_quoted = vlm_text.replace('\n', '\n> ')
                                replacement = f"![Diagram]({rel_to_md})\n\n> **Image Analysis (via {self.vlm_model}):**\n> {vlm_quoted}\n"
                                page_md = page_md.replace(
                                    match.group(0), replacement)
                                images_processed += 1
                            except Exception as e:
                                console.print(
                                    f"[red]Error analyzing image {img_full_path.name}: {e}[/red]")

                    md_text_chunks.append(page_md)
                    progress.update(
                        task,
                        advance=1,
                        description=f"[cyan]Hybrid Parsing {pdf_path_obj.name} (Page-by-Page)...")

            doc.close()
            md_text = "\n\n".join(md_text_chunks)
            console.print(
                f"[green]Hybrid Extraction Complete: {images_processed} diagrams analyzed, {images_deleted} decorative/background images deleted.[/green]")
            return self._build_doc(
                pdf_path_obj,
                md_text,
                images_processed,
                images_deleted)

        finally:
            # Cleanup temp directory
            if temp_img_dir.exists():
                shutil.rmtree(temp_img_dir, ignore_errors=True)

    def _build_doc(self, pdf_path_obj, md_text, img_processed, img_deleted):
        try:
            version_mupdf = importlib.metadata.version("pymupdf4llm")
        except BaseException:
            version_mupdf = "unknown"

        try:
            version_ollama = importlib.metadata.version("ollama")
        except BaseException:
            version_ollama = "unknown"

        metadata = {
            "source": pdf_path_obj.name,
            "page_count": "Unknown (Hybrid)",
            "date_ingested": datetime.now().replace(
                microsecond=0).isoformat(' '),
            "extractor": {
                "program": "Hybrid (pymupdf4llm + ollama)",
                "version": f"mupdf:{version_mupdf}, ollama:{version_ollama}",
                "vlm_model": self.vlm_model,
                "mode": "hybrid_pdf",
                "dpi": self.dpi,
                "images_analyzed": img_processed,
                "images_discarded": img_deleted}}
        return Document(
            source_file=pdf_path_obj.name,
            content=md_text,
            metadata=metadata)

import json
import asyncio
from pydantic import BaseModel, Field

class ImageDescription(BaseModel):
    filename: str = Field(description="The exact filename provided in the prompt")
    description: str = Field(description="The detailed markdown description of the image")

class ImageDescriptions(BaseModel):
    descriptions: list[ImageDescription] = Field(description="A list of image descriptions")

class FreeTierMegaBatchExtractor(BaseExtractor):
    """Tier 4 Extractor: Mega-Batch VLM OCR for Free Tier API limits."""
    
    def __init__(self, **kwargs):
        self.vlm_model = kwargs.get("vlm_model", "gemini-3.6-flash")
        self.min_image_pixels = kwargs.get("min_image_pixels", 25000)
        self.max_image_pixels = kwargs.get("max_image_pixels", 2000000)
        self.dpi = kwargs.get("dpi", 300)
        self.prompt = (
            "You are an expert data extraction engine. I am providing you with multiple images. "
            "Describe each image in detail. If it contains data, charts, tables, or text, transcribe them perfectly as Markdown. "
            "Return the descriptions as a JSON dictionary mapping the exact filename to the description."
        )
        
        self.use_gemini = False
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and "gemini" in self.vlm_model.lower():
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=api_key)
                self.use_gemini = True
            except Exception as e:
                console.print(f"[red]Failed to initialize Gemini: {e}[/red]")
                
        if not self.use_gemini:
            raise ValueError("FreeTierMegaBatchExtractor requires a valid Gemini API Key and Model.")

    def extract(self, file_path: str, **kwargs) -> Document:
        import shutil
        import tempfile
        import pymupdf
        from google.genai import types

        pdf_path_obj = Path(file_path)
        output_dir_str = kwargs.get("output_dir", "data/staging/staging_markdown")
        output_dir = Path(output_dir_str)

        assets_base_dir = output_dir.parent / "assets"
        doc_asset_dir = assets_base_dir / pdf_path_obj.stem
        doc_asset_dir.mkdir(parents=True, exist_ok=True)

        temp_img_dir = Path(tempfile.mkdtemp())
        
        all_images_to_process = []
        md_text_chunks = []
        images_deleted = 0

        try:
            doc = pymupdf.open(file_path)
            total_pages = len(doc)

            with console.status(f"[cyan]Ripping images from {total_pages} pages...[/cyan]"):
                for page_num in range(total_pages):
                    page_md = pymupdf4llm.to_markdown(
                        doc,
                        pages=[page_num],
                        write_images=True,
                        image_path=str(temp_img_dir),
                        dpi=self.dpi
                    )

                    image_pattern = re.compile(r'!\[.*?\]\((.*?)\)')
                    matches = list(image_pattern.finditer(page_md))

                    for match in matches:
                        img_rel_path = match.group(1)
                        img_full_path = Path(img_rel_path)

                        if not img_full_path.is_absolute():
                            if (temp_img_dir / img_full_path.name).exists():
                                img_full_path = temp_img_dir / img_full_path.name

                        if not img_full_path.exists():
                            continue

                        try:
                            with Image.open(img_full_path) as img:
                                width, height = img.size
                                pixels = width * height
                        except Exception:
                            continue

                        if pixels < self.min_image_pixels:
                            try:
                                img_full_path.unlink(missing_ok=True)
                            except BaseException:
                                pass
                            page_md = page_md.replace(match.group(0), "")
                            images_deleted += 1
                        else:
                            # Move to final asset dir immediately
                            final_img_path = doc_asset_dir / img_full_path.name
                            shutil.move(str(img_full_path), str(final_img_path))
                            
                            all_images_to_process.append({
                                'filename': img_full_path.name,
                                'path': final_img_path,
                                'match_str': match.group(0)
                            })
                            
                    md_text_chunks.append(page_md)
            doc.close()

            if not all_images_to_process:
                md_text = "\n\n".join(md_text_chunks)
                return self._build_doc(pdf_path_obj, md_text, 0, images_deleted)

            # --- MEGA BATCH INFERENCE ---
            console.print(f"[bold yellow]Initiating Mega-Batch API Request for {len(all_images_to_process)} images...[/bold yellow]")
            contents = [self.prompt]
            
            # Load all images into memory
            for img_info in all_images_to_process:
                with open(img_info['path'], "rb") as f:
                    image_bytes = f.read()
                contents.append(f"Filename: {img_info['filename']}")
                contents.append(types.Part.from_bytes(data=image_bytes, mime_type='image/png'))

            # Send single massive request
            try:
                response = self.gemini_client.models.generate_content(
                    model=self.vlm_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ImageDescriptions,
                        temperature=0.0
                    )
                )
                
                # Parse structured JSON output
                response_json = json.loads(response.text)
                desc_list = response_json.get("descriptions", [])
                # Convert back to dict for easy lookup
                descriptions = {item["filename"]: item["description"] for item in desc_list}
                
            except Exception as e:
                console.print(f"[red]Mega-Batch API Error: {e}[/red]")
                descriptions = {}

            # Inject back into markdown chunks
            for i in range(len(md_text_chunks)):
                for img_info in all_images_to_process:
                    if img_info['match_str'] in md_text_chunks[i]:
                        desc = descriptions.get(img_info['filename'], "[OCR FAILED]")
                        
                        try:
                            rel_to_md = os.path.relpath(img_info['path'], output_dir).replace("\\", "/")
                        except ValueError:
                            rel_to_md = str(img_info['path'].resolve()).replace("\\", "/")

                        vlm_quoted = desc.replace('\n', '\n> ')
                        replacement = f"![Diagram]({rel_to_md})\n\n> **Image Analysis (via MegaBatch):**\n> {vlm_quoted}\n"
                        md_text_chunks[i] = md_text_chunks[i].replace(img_info['match_str'], replacement)

            md_text = "\n\n".join(md_text_chunks)
            console.print(f"[green]Mega-Batch Extraction Complete: {len(all_images_to_process)} images mapped.[/green]")
            return self._build_doc(pdf_path_obj, md_text, len(all_images_to_process), images_deleted)

        finally:
            if temp_img_dir.exists():
                shutil.rmtree(temp_img_dir, ignore_errors=True)

    def _build_doc(self, pdf_path_obj, md_text, img_processed, img_deleted):
        metadata = {
            "source": pdf_path_obj.name,
            "extractor": {
                "program": "FreeTierMegaBatchExtractor",
                "vlm_model": self.vlm_model,
                "images_analyzed": img_processed,
                "images_discarded": img_deleted
            }
        }
        return Document(source_file=pdf_path_obj.name, content=md_text, metadata=metadata)


class EnterpriseBatchExtractor(BaseExtractor):
    """Tier 5 Extractor: Dispatches OpenAI/Anthropic/Gemini compatible JSONL for Async 50% discount Batch processing."""
    
    def __init__(self, **kwargs):
        self.provider = kwargs.get("provider", "gemini").lower()
        self.vlm_model = kwargs.get("vlm_model", "gemini-3.7-flash")
        self.min_image_pixels = kwargs.get("min_image_pixels", 25000)
        self.dpi = kwargs.get("dpi", 300)
        self.prompt = (
            "You are an expert data extraction engine. Describe this image in detail. "
            "If it contains data, charts, tables, or text, transcribe them perfectly as Markdown. "
            "Do not include conversational filler."
        )

    def extract(self, file_path: str, **kwargs) -> Document:
        import shutil
        import tempfile
        import pymupdf
        import base64
        import json
        from src.extractors.batch_manager import BatchManager

        pdf_path_obj = Path(file_path)
        output_dir_str = kwargs.get("output_dir", "data/staging/staging_markdown")
        output_dir = Path(output_dir_str)

        assets_base_dir = output_dir.parent / "assets"
        doc_asset_dir = assets_base_dir / pdf_path_obj.stem
        doc_asset_dir.mkdir(parents=True, exist_ok=True)
        
        batch_jobs_dir = output_dir.parent / "batch_jobs"
        batch_jobs_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = batch_jobs_dir / f"{pdf_path_obj.stem}_job.jsonl"
        jobstate_path = batch_jobs_dir / f"{pdf_path_obj.stem}.jobstate"

        temp_img_dir = Path(tempfile.mkdtemp())
        
        all_images_to_process = []
        md_text_chunks = []
        images_deleted = 0

        try:
            doc = pymupdf.open(file_path)
            total_pages = len(doc)

            with console.status(f"[cyan]Ripping images to generate {self.provider.upper()} JSONL Batch Job...[/cyan]"):
                for page_num in range(total_pages):
                    page_md = pymupdf4llm.to_markdown(
                        doc,
                        pages=[page_num],
                        write_images=True,
                        image_path=str(temp_img_dir),
                        dpi=self.dpi
                    )

                    image_pattern = re.compile(r'!\[.*?\]\((.*?)\)')
                    matches = list(image_pattern.finditer(page_md))

                    for match in matches:
                        img_rel_path = match.group(1)
                        img_full_path = Path(img_rel_path)

                        if not img_full_path.is_absolute():
                            if (temp_img_dir / img_full_path.name).exists():
                                img_full_path = temp_img_dir / img_full_path.name

                        if not img_full_path.exists():
                            continue

                        try:
                            with Image.open(img_full_path) as img:
                                width, height = img.size
                                pixels = width * height
                        except Exception:
                            continue

                        if pixels < self.min_image_pixels:
                            try:
                                img_full_path.unlink(missing_ok=True)
                            except BaseException:
                                pass
                            page_md = page_md.replace(match.group(0), "")
                            images_deleted += 1
                        else:
                            final_img_path = doc_asset_dir / img_full_path.name
                            shutil.move(str(img_full_path), str(final_img_path))
                            
                            all_images_to_process.append({
                                'filename': img_full_path.name,
                                'path': final_img_path,
                                'match_str': match.group(0)
                            })
                            
                    md_text_chunks.append(page_md)

            # Generate Provider-Specific JSONL
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for img_info in all_images_to_process:
                    with open(img_info['path'], "rb") as img_file:
                        b64_img = base64.b64encode(img_file.read()).decode('utf-8')
                    
                    if self.provider == "gemini":
                        # Google GenAI Batch SDK allows OpenAI compatibility, but native format is simpler
                        req = {
                            "custom_id": img_info['filename'],
                            "method": "POST",
                            "url": "/v1/chat/completions",
                            "body": {
                                "model": self.vlm_model,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": self.prompt},
                                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
                                        ]
                                    }
                                ]
                            }
                        }
                    elif self.provider == "openai":
                        req = {
                            "custom_id": img_info['filename'],
                            "method": "POST",
                            "url": "/v1/chat/completions",
                            "body": {
                                "model": self.vlm_model,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": self.prompt},
                                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
                                        ]
                                    }
                                ]
                            }
                        }
                    elif self.provider == "anthropic":
                        req = {
                            "custom_id": img_info['filename'],
                            "params": {
                                "model": self.vlm_model,
                                "max_tokens": 1024,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "image",
                                                "source": {
                                                    "type": "base64",
                                                    "media_type": "image/png",
                                                    "data": b64_img
                                                }
                                            },
                                            {"type": "text", "text": self.prompt}
                                        ]
                                    }
                                ]
                            }
                        }
                    
                    f.write(json.dumps(req) + "
")

            console.print(f"[green]Successfully generated Batch Job JSONL: {jsonl_path}[/green]")
            
            # Dispatch the batch job
            manager = BatchManager(provider=self.provider)
            try:
                job_id = manager.submit_job(str(jsonl_path))
            except Exception as e:
                console.print(f"[red]Failed to submit batch job: {e}[/red]")
                job_id = "FAILED_TO_SUBMIT"

            # Save the job state for later injection
            jobstate = {
                "job_id": job_id,
                "provider": self.provider,
                "pdf_path": str(pdf_path_obj),
                "output_dir": str(output_dir),
                "images": [{k: str(v) for k, v in img.items()} for img in all_images_to_process],
                "md_text_chunks": md_text_chunks
            }
            with open(jobstate_path, 'w', encoding='utf-8') as f:
                json.dump(jobstate, f, indent=2)

            return Document(
                source_file=pdf_path_obj.name,
                content=f"<!-- BATCH JOB PENDING: {job_id} -->

Please run the batch resolution script when the job is completed to inject the results.",
                metadata={"status": "Awaiting Batch Completion", "job_id": job_id}
            )

        finally:
            if temp_img_dir.exists():
                shutil.rmtree(temp_img_dir, ignore_errors=True)
