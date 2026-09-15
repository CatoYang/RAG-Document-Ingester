import pymupdf

from src.extract.pdf_density import average_chars_per_page, has_text_layer


def _make_pdf(path, page_texts):
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_average_chars_per_page_on_text_pdf(tmp_path):
    pdf_path = tmp_path / "text.pdf"
    _make_pdf(pdf_path, [
        "This is a page with a substantial amount of real body text on it, " * 5,
        "This is a page with a substantial amount of real body text on it, " * 5,
    ])

    avg = average_chars_per_page(str(pdf_path))

    assert avg > 100


def test_average_chars_per_page_on_blank_pdf(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    _make_pdf(pdf_path, ["", ""])  # simulates an image-only scan with no text layer

    avg = average_chars_per_page(str(pdf_path))

    assert avg == 0.0


def test_has_text_layer_thresholds(tmp_path):
    text_pdf = tmp_path / "text.pdf"
    _make_pdf(text_pdf, ["Real embedded text content here, plenty of it. " * 5])
    scanned_pdf = tmp_path / "scanned.pdf"
    _make_pdf(scanned_pdf, [""])

    assert has_text_layer(str(text_pdf)) is True
    assert has_text_layer(str(scanned_pdf)) is False


def test_has_text_layer_missing_file_returns_false():
    assert has_text_layer("/nonexistent/path/does-not-exist.pdf") is False
