from pathlib import Path
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document
from src.extract.pdf_density import average_chars_per_page
from src.extract.pdf_text import PyMuPDF4LLMExtractor

console = Console()


class AutoPdfExtractor(BaseExtractor):
    """Routes a PDF to a fast CPU-only extractor if it has a usable text
    layer, or to a GPU OCR extractor (default: PdfExtractor/Marker) if it
    looks like an image-only scan.

    The OCR extractor is constructed lazily - only on the first PDF that
    actually needs it - so a directory of mostly text-layer PDFs never pays
    for loading Marker's models at all. On this project's hardware, loading
    Marker is the expensive, GPU-bound step (see CLAUDE.md); don't run this
    extractor unattended over a directory containing scans without expecting
    that cost.
    """

    def __init__(self, min_avg_chars_per_page: float = 100.0, pages_to_check: int = 5,
                 ocr_extractor: str = "PdfExtractor", ocr_params: dict = None, **kwargs):
        self.min_avg_chars_per_page = min_avg_chars_per_page
        self.pages_to_check = pages_to_check
        self.ocr_extractor_name = ocr_extractor
        self.ocr_params = ocr_params or {}
        self._text_extractor = PyMuPDF4LLMExtractor()
        self._ocr_extractor: BaseExtractor = None  # lazy - see class docstring

    def _get_ocr_extractor(self) -> BaseExtractor:
        if self._ocr_extractor is None:
            from src.extract.registry import get_extractor_class
            console.print(f"[yellow]Loading OCR extractor '{self.ocr_extractor_name}' (first scanned PDF this run)...[/yellow]")
            extractor_cls = get_extractor_class(self.ocr_extractor_name)
            self._ocr_extractor = extractor_cls(**self.ocr_params)
        return self._ocr_extractor

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)

        try:
            density = average_chars_per_page(str(file_path_obj), self.pages_to_check)
        except Exception as e:
            console.print(f"[yellow]Could not measure text density for {file_path_obj.name} ({e}); routing to OCR.[/yellow]")
            density = 0.0

        if density >= self.min_avg_chars_per_page:
            console.print(f"[dim]{file_path_obj.name}: avg {density:.0f} chars/page - has a text layer, using fast extractor.[/dim]")
            doc = self._text_extractor.extract(file_path, **kwargs)
        else:
            console.print(f"[dim]{file_path_obj.name}: avg {density:.0f} chars/page - looks scanned, routing to OCR extractor.[/dim]")
            doc = self._get_ocr_extractor().extract(file_path, **kwargs)

        doc.metadata.setdefault("extractor", {})["auto_routing"] = {
            "avg_chars_per_page": round(density, 1),
            "threshold": self.min_avg_chars_per_page,
        }
        return doc
