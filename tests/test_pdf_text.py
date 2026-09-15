import pymupdf

from src.extract.pdf_text import PyMuPDF4LLMExtractor, PAGE_MARKER_PATTERN


def _make_pdf(path, page_texts):
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_extract_emits_page_markers_and_content(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, [
        "Page one content about clans and disciplines.",
        "Page two content about houses and dragonmarks.",
    ])

    extractor = PyMuPDF4LLMExtractor()
    doc = extractor.extract(str(pdf_path), output_dir=str(tmp_path))

    assert doc.metadata["extractor"]["program"] == "pymupdf4llm"
    assert doc.metadata["extractor"]["pages"] == 2
    assert "error" not in doc.metadata

    page_numbers = [int(m) for m in PAGE_MARKER_PATTERN.findall(doc.content)]
    assert page_numbers == [1, 2]
    assert "clans and disciplines" in doc.content
    assert "houses and dragonmarks" in doc.content


def test_extract_on_broken_file_returns_error_document(tmp_path):
    bad_path = tmp_path / "not_a_pdf.pdf"
    bad_path.write_text("this is not a valid PDF")

    extractor = PyMuPDF4LLMExtractor()
    doc = extractor.extract(str(bad_path))

    assert doc.content == ""
    assert "error" in doc.metadata
