import os
import subprocess
from pathlib import Path
from datetime import datetime
import pymupdf
import pymupdf4llm
import ollama
import importlib.metadata
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

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
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "pymupdf4llm",
                "version": version,
                "mode": "pdf_text"
            }
        }
        
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
            "Output ONLY the transcribed markdown."
        )

    def _get_ollama_client(self):
        """Returns an Ollama client, automatically adjusting for WSL2 networking."""
        host = "http://127.0.0.1:11434"
        if "WSL_DISTRO_NAME" in os.environ:
            try:
                result = subprocess.run(['ip', 'route'], capture_output=True, text=True, check=True)
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
            task = progress.add_task(f"[cyan]Extracting {page_count} pages with {self.model}...", total=page_count)
            
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
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "ollama",
                "version": version,
                "model": self.model,
                "mode": "pdf_vision",
                "dpi": self.dpi,
            }
        }
        if self.temperature is not None:
            metadata["extractor"]["temperature"] = self.temperature
        
        return Document(
            source_file=pdf_path_obj.name,
            content=md_text,
            metadata=metadata
        )
