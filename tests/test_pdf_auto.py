import pymupdf
import pytest

from src.core.interfaces import BaseExtractor, Document
from src.extract.pdf_auto import AutoPdfExtractor
from src.extract.registry import EXTRACTOR_REGISTRY


def _make_pdf(path, page_texts):
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


class _StubOcrExtractor(BaseExtractor):
    """Stands in for PdfExtractor/Marker in tests, so routing to the OCR
    path never actually loads Marker's models (which requires asking the
    user first on this project - see CLAUDE.md)."""
    instances_created = 0

    def __init__(self, **kwargs):
        _StubOcrExtractor.instances_created += 1
        self.params = kwargs

    def extract(self, file_path: str, **kwargs) -> Document:
        return Document(source_file=file_path, content="stub ocr output", metadata={"extractor": {"program": "stub"}})


@pytest.fixture(autouse=True)
def _register_stub_ocr_extractor():
    EXTRACTOR_REGISTRY["_StubOcrExtractor"] = _StubOcrExtractor
    _StubOcrExtractor.instances_created = 0
    yield
    del EXTRACTOR_REGISTRY["_StubOcrExtractor"]


def test_auto_pdf_extractor_routes_text_layer_pdf_to_fast_path(tmp_path):
    pdf_path = tmp_path / "text.pdf"
    _make_pdf(pdf_path, ["Plenty of real embedded text content here, over and over. " * 5])

    extractor = AutoPdfExtractor(ocr_extractor="_StubOcrExtractor")
    doc = extractor.extract(str(pdf_path), output_dir=str(tmp_path))

    assert doc.metadata["extractor"]["program"] == "pymupdf4llm"
    assert doc.metadata["extractor"]["auto_routing"]["avg_chars_per_page"] > 100
    assert _StubOcrExtractor.instances_created == 0  # never loaded


def test_auto_pdf_extractor_routes_scanned_pdf_to_ocr_path(tmp_path):
    pdf_path = tmp_path / "scanned.pdf"
    _make_pdf(pdf_path, [""])  # no text layer

    extractor = AutoPdfExtractor(ocr_extractor="_StubOcrExtractor")
    doc = extractor.extract(str(pdf_path), output_dir=str(tmp_path))

    assert doc.content == "stub ocr output"
    assert doc.metadata["extractor"]["program"] == "stub"
    assert doc.metadata["extractor"]["auto_routing"]["avg_chars_per_page"] == 0.0
    assert _StubOcrExtractor.instances_created == 1


def test_auto_pdf_extractor_only_loads_ocr_extractor_once(tmp_path):
    scanned_a = tmp_path / "scanned_a.pdf"
    scanned_b = tmp_path / "scanned_b.pdf"
    _make_pdf(scanned_a, [""])
    _make_pdf(scanned_b, [""])

    extractor = AutoPdfExtractor(ocr_extractor="_StubOcrExtractor")
    extractor.extract(str(scanned_a), output_dir=str(tmp_path))
    extractor.extract(str(scanned_b), output_dir=str(tmp_path))

    assert _StubOcrExtractor.instances_created == 1
