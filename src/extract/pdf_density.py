"""Shared PDF text-density heuristic.

Used to decide whether a PDF's embedded text layer is usable (fast CPU-only
extraction via `pymupdf4llm`) or whether the PDF is effectively a set of
scanned images and needs real OCR (Marker/Surya, GPU, much slower). This was
previously duplicated as `DocumentRouter._check_pdf_text_density`
(src/extract/factory.py), which nothing called; it now backs
`AutoPdfExtractor` (src/extract/pdf_auto.py).
"""
import pymupdf


def average_chars_per_page(file_path: str, pages_to_check: int = 5) -> float:
    """Returns the average character count of the first `pages_to_check`
    pages' extracted text. A PDF with a real text layer will read in the
    thousands of characters per page; an image-only scan will read near 0."""
    doc = pymupdf.open(file_path)
    try:
        sample_size = min(pages_to_check, len(doc))
        if sample_size == 0:
            return 0.0

        total_chars = sum(
            len(doc.load_page(i).get_text().strip())
            for i in range(sample_size)
        )
        return total_chars / sample_size
    finally:
        doc.close()


def has_text_layer(file_path: str, pages_to_check: int = 5, min_avg_chars_per_page: float = 100.0) -> bool:
    """True if the PDF has a usable embedded text layer, False if it looks
    like an image-only scan that needs OCR."""
    try:
        return average_chars_per_page(file_path, pages_to_check) >= min_avg_chars_per_page
    except Exception:
        # If we can't even open/sample the PDF, don't guess - let the caller's
        # own extraction attempt surface the real error.
        return False
