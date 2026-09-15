import re
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import BaseExtractor, Document

console = Console()

# Emitted once per page, immediately before that page's text. Deliberately
# NOT the "<!-- PAGE N -->" (uppercase, no colon) format some configs already
# strip via cleanup_rules.regex_removals (that pattern predates this
# extractor and targeted a different, unrelated artifact) - this marker is
# meant to survive cleaning so MarkdownChunker (src/index/chunkers.py) can
# recover per-chunk page numbers from it via PAGE_MARKER_PATTERN.
PAGE_MARKER_TEMPLATE = "<!-- page_number: {page} -->"
PAGE_MARKER_PATTERN = re.compile(r'<!-- page_number: (\d+) -->')


class PyMuPDF4LLMExtractor(BaseExtractor):
    """Tier 1 Extractor: fast, CPU-only Markdown extraction for PDFs that
    already have a usable embedded text layer (measured ~0.25s/page on this
    project's hardware - see CLAUDE.md). Does not perform OCR and does not
    extract embedded images; PDFs without a real text layer should route to
    an OCR-capable extractor (e.g. PdfExtractor/Marker) instead - see
    AutoPdfExtractor (src/extract/pdf_auto.py), which picks between the two."""

    def __init__(self, **kwargs):
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        import pymupdf4llm

        file_path_obj = Path(file_path)
        console.print(f"[cyan]Extracting text-layer PDF {file_path_obj.name} (pymupdf4llm)...[/cyan]")

        try:
            pages = pymupdf4llm.to_markdown(str(file_path_obj), page_chunks=True, show_progress=False)
        except Exception as e:
            console.print(f"[red]Error extracting PDF {file_path_obj.name}: {e}[/red]")
            return Document(source_file=file_path_obj.name, content="", metadata={"error": str(e)})

        parts = []
        for page in pages:
            page_number = page.get("metadata", {}).get("page_number")
            if page_number is not None:
                parts.append(PAGE_MARKER_TEMPLATE.format(page=page_number))
            parts.append(page.get("text", ""))
        content = "\n\n".join(parts)

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(microsecond=0).isoformat(' '),
            "extractor": {
                "program": "pymupdf4llm",
                "mode": "text_layer",
                "pages": len(pages),
            },
        }

        console.print(f"[green]Extracted {len(pages)} pages from {file_path_obj.name} (text layer, CPU-only)[/green]")

        return Document(source_file=file_path_obj.name, content=content, metadata=metadata)
