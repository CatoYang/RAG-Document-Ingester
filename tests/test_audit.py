"""Source audit (TODO.md Path T1): filename parsing, PDF/EPUB measurements,
the recommendation rule and the manifest. Every fixture is generated in
tmp_path - no real books, no network."""
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import pymupdf
import pytest
import yaml

from src.audit.epub import audit_epub
from src.audit.filename import find_isbns, parse_archive_filename
from src.audit.manifest import load_manifest, merge_title, save_manifest
from src.audit.pdf import audit_pdf
from src.audit.recommend import audit_book, recommend, same_edition

BODY = "Body text of a textbook page with enough characters to count as a real text layer. " * 4


# --- fixtures -----------------------------------------------------------------

def make_pdf(path: Path, pages: int = 10, producer: str = "pdfTeX-1.40.21", printed_offset: Optional[int] = 4,
             scan: bool = False, scan_text: bool = False, toc: Optional[list] = None,
             isbn: Optional[str] = "978-3-030-96623-2") -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        if scan:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
            pix.clear_with(200)
            page.insert_image(page.rect, pixmap=pix)
            if scan_text:  # invisible OCR layer, as ABBYY/Tesseract output has
                page.insert_textbox(page.rect + (36, 36, -36, -36), BODY, render_mode=3)
            continue
        header = f"{i + 1 - printed_offset}\nCHAPTER 1. INTRODUCTION\n" \
            if printed_offset is not None and i >= printed_offset else "CHAPTER 1. INTRODUCTION\n"
        text = header + (f"ISBN {isbn}\n" if isbn and i == 0 else "")
        page.insert_text((72, 72), text)
        page.insert_textbox(pymupdf.Rect(72, 120, 540, 700), BODY)
    doc.set_metadata({"producer": producer})
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
{body}
</body></html>"""

GOOD_CHAPTER = CHAPTER.format(body="""
<h1>1 Introduction</h1><p>Some text about vectors.</p>
<span epub:type="pagebreak" id="p1" title="1"/>
<h2>1.1 Vectors</h2><p>Let <img alt="$$\\overline{X}$$" src="../images/c1_TeX_IEq1.png"/> be a vector.</p>
<div class="Equation"><img alt="$$\\sum_i x_i$$" src="../images/c1_TeX_Equ1.png"/></div>
<div class="Figure"><img alt="" src="../images/c1_Fig1_HTML.png"/></div>
<table><tr><td>a</td></tr></table>""")


def make_epub(path: Path, chapters: Optional[Dict[str, str]] = None, metadata: str = "",
              page_list: bool = True, encryption: Optional[str] = None, rights: bool = False,
              identifier: str = "urn:isbn:978-3-030-96623-2") -> Path:
    chapters = chapters if chapters is not None else {"ch1.xhtml": GOOD_CHAPTER}
    manifest = "".join(f'<item id="c{i}" href="html/{name}" media-type="application/xhtml+xml"/>'
                       for i, name in enumerate(chapters))
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
    toc = "".join(f'<li><a href="html/{name}">{name}</a></li>' for name in chapters)
    pages = '<nav epub:type="page-list"><ol><li><a href="html/ch1.xhtml#p1">1</a></li></ol></nav>' \
        if page_list else ""
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0">
<metadata><dc:identifier>{identifier}</dc:identifier><dc:title>Test Book</dc:title>
<dc:creator>A. Author</dc:creator><dc:publisher>Test Publisher</dc:publisher>{metadata}</metadata>
<manifest><item id="nav" properties="nav" href="nav.xhtml" media-type="application/xhtml+xml"/>{manifest}</manifest>
<spine>{spine}</spine></package>"""
    nav = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol>{toc}</ol></nav>{pages}</body></html>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        z.writestr("OEBPS/package.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        for name, content in chapters.items():
            z.writestr(f"OEBPS/html/{name}", content)
        if encryption:
            z.writestr("META-INF/encryption.xml", f"""<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
<enc:EncryptedData><enc:EncryptionMethod Algorithm="{encryption}"/>
<enc:CipherData><enc:CipherReference URI="OEBPS/html/ch1.xhtml"/></enc:CipherData></enc:EncryptedData>
</encryption>""")
        if rights:
            z.writestr("META-INF/rights.xml", "<rights/>")
    return path


# --- filename -----------------------------------------------------------------

def test_parse_full_archive_filename():
    name = ("Machine Learning for Text -- Charu C. Aggarwal -- 2nd ed. 2022, 2022 -- Springer -- "
            "9783030966225, 978-3-030-96623-2 -- fa5f172a16e8958d81ff3a41d8dc0780 -- Anna’s Archive.epub")
    parsed = parse_archive_filename(name)
    assert parsed["is_archive_name"] is True
    assert parsed["title"] == "Machine Learning for Text"
    assert parsed["authors"] == "Charu C. Aggarwal"
    assert parsed["isbns"] == ["9783030966225", "9783030966232"]
    assert parsed["md5"] == "fa5f172a16e8958d81ff3a41d8dc0780"
    assert parsed["year"] == 2022
    assert parsed["other"] == ["2nd ed. 2022, 2022", "Springer"]


def test_parse_renamed_file_is_just_a_title():
    parsed = parse_archive_filename("Machine Learning for Text.pdf")
    assert parsed["is_archive_name"] is False
    assert parsed["title"] == "Machine Learning for Text"
    assert parsed["isbns"] == [] and parsed["md5"] is None


def test_find_isbns_handles_hyphens_and_isbn10():
    assert find_isbns("ISBN 978-3-030-96622-5 (print), ISBN 0-306-40615-2") == ["9783030966225", "0306406152"]


# --- PDF ----------------------------------------------------------------------

def test_audit_typeset_pdf(tmp_path):
    pdf = make_pdf(tmp_path / "book.pdf", toc=[[1, "1 Intro", 1], [2, "1.1 Vectors", 2],
                                               [3, "1.1.1 Norms", 3], [1, "Index", 9]])
    m = audit_pdf(str(pdf))
    assert m["origin"] == "typeset"
    assert m["text"]["has_text_layer"] is True
    assert m["structure"] == {"toc_entries": 4, "toc_depth": 3}
    assert m["page_citations"]["printed_pages"]["detected"] is True
    assert m["page_citations"]["printed_pages"]["offset"] == 4
    assert m["back_matter"] == [{"title": "Index", "pages": [9, 10]}]
    assert m["isbns"] == ["9783030966232"]


def test_audit_converted_pdf(tmp_path):
    m = audit_pdf(str(make_pdf(tmp_path / "book.pdf", producer="calibre 6.11.0")))
    assert m["origin"] == "converted"


def test_audit_scanned_pdfs(tmp_path):
    image_only = audit_pdf(str(make_pdf(tmp_path / "scan.pdf", scan=True)))
    assert image_only["origin"] == "scan_image_only"
    assert image_only["text"]["has_text_layer"] is False

    with_ocr = audit_pdf(str(make_pdf(tmp_path / "ocr.pdf", scan=True, scan_text=True)))
    assert with_ocr["origin"] == "scan_ocr"
    assert with_ocr["text"]["has_text_layer"] is True


def test_audit_pdf_without_page_numbers(tmp_path):
    m = audit_pdf(str(make_pdf(tmp_path / "book.pdf", printed_offset=None)))
    assert m["page_citations"]["printed_pages"]["detected"] is False


# --- EPUB ---------------------------------------------------------------------

def test_audit_publisher_epub(tmp_path):
    m = audit_epub(str(make_epub(tmp_path / "book.epub")))
    assert m["origin"] == "publisher"
    assert m["drm"] is False and m["layout"] == "reflowable"
    assert m["structure"]["headings"]["h1"] == 1 and m["structure"]["headings"]["h2"] == 1
    assert m["structure"]["documents_with_headings"] == 1
    assert m["maths"]["mode"] == "latex_alt_text"
    assert m["maths"]["equation_images"] == 2 and m["maths"]["tex_alt_images"] == 2
    assert m["figures"] == 1 and m["tables"] == 1
    assert m["page_citations"] == {"page_list_entries": 1, "page_break_markers": 1}
    assert m["isbns"] == ["9783030966232"]


def test_audit_epub_ignores_non_isbn_identifiers(tmp_path):
    m = audit_epub(str(make_epub(tmp_path / "b.epub", identifier="urn:uuid:12345678-1234-1234-1234-123456789012")))
    assert m["isbns"] == []


def test_audit_calibre_epub_is_converted(tmp_path):
    m = audit_epub(str(make_epub(tmp_path / "b.epub",
                                 metadata='<meta name="calibre:timestamp" content="2020-01-01"/>')))
    assert m["origin"] == "converted"


def test_audit_epub_drm_vs_font_obfuscation(tmp_path):
    drm = audit_epub(str(make_epub(tmp_path / "drm.epub",
                                   encryption="http://www.w3.org/2001/04/xmlenc#aes128-cbc")))
    assert drm["drm"] is True
    fonts = audit_epub(str(make_epub(tmp_path / "fonts.epub", encryption="http://www.idpf.org/2008/embedding")))
    assert fonts["drm"] is False
    adept = audit_epub(str(make_epub(tmp_path / "adept.epub", rights=True)))
    assert adept["drm"] is True


def test_audit_fixed_layout_and_mathml_epub(tmp_path):
    chapter = CHAPTER.format(body='<h1>1</h1><p><math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math></p>')
    m = audit_epub(str(make_epub(tmp_path / "b.epub", chapters={"ch1.xhtml": chapter},
                                 metadata='<meta property="rendition:layout">pre-paginated</meta>')))
    assert m["layout"] == "fixed"
    assert m["maths"]["mode"] == "mathml"


def test_audit_epub_equation_images_without_source(tmp_path):
    chapter = CHAPTER.format(body="<h1>1</h1>" + "".join(
        f'<div class="Equation"><img alt="" src="../images/c1_Equ{i}_HTML.png"/></div>' for i in range(30)))
    m = audit_epub(str(make_epub(tmp_path / "b.epub", chapters={"ch1.xhtml": chapter})))
    assert m["maths"]["mode"] == "images_no_source"
    assert m["maths"]["equation_images"] == 30


# --- recommendation -----------------------------------------------------------

def _book(tmp_path: Path, **files) -> Dict[str, dict]:
    book = tmp_path / "book"
    book.mkdir()
    for name, maker in files.items():
        maker(book / name.replace("_", "."))
    return audit_book(book)


def test_good_epub_beats_pdf_and_points_to_pdf_page_map(tmp_path):
    no_pages = {"ch1.xhtml": GOOD_CHAPTER.replace('<span epub:type="pagebreak" id="p1" title="1"/>', "")}
    candidates = _book(tmp_path, book_pdf=make_pdf,
                       book_epub=lambda p: make_epub(p, chapters=no_pages, page_list=False))
    rec = recommend(candidates)
    assert rec["file"] == "book.epub" and rec["extraction"] == "epub_structured"
    assert any("book.pdf has printed page numbers" in c for c in rec["caveats"])
    assert "book.pdf" in rec["alternatives"]
    assert rec["same_edition"]["status"] == "match"


def test_drm_epub_is_rejected(tmp_path):
    candidates = _book(tmp_path, book_pdf=make_pdf,
                       book_epub=lambda p: make_epub(p, encryption="http://www.w3.org/2001/04/xmlenc#aes128-cbc"))
    rec = recommend(candidates)
    assert rec["file"] == "book.pdf" and rec["extraction"] == "pdf_text_layer"
    assert "book.epub" in rec["rejected"]


def test_converted_epub_loses_to_typeset_pdf(tmp_path):
    candidates = _book(tmp_path, book_pdf=make_pdf, book_epub=lambda p: make_epub(
        p, metadata='<meta name="generator" content="calibre (6.11.0)"/>'))
    assert recommend(candidates)["file"] == "book.pdf"


def test_image_only_scan_recommends_ocr_with_warning(tmp_path):
    candidates = _book(tmp_path, scan_pdf=lambda p: make_pdf(p, scan=True))
    rec = recommend(candidates)
    assert rec["extraction"] == "pdf_ocr"
    assert "GPU-heavy" in rec["caveats"][0]


def test_unsupported_and_corrupt_files_are_rejected(tmp_path):
    def djvu(p):
        p.write_bytes(b"AT&TFORM")

    def broken_epub(p):
        p.write_bytes(b"not a zip")

    rec = recommend(_book(tmp_path, book_djvu=djvu, book_epub=broken_epub))
    assert rec["file"] is None
    assert set(rec["rejected"]) == {"book.djvu", "book.epub"}


def test_same_edition_statuses():
    def cand(isbns: List[str]) -> dict:
        return {"isbns": isbns, "filename_metadata": {"isbns": []}}

    assert same_edition({"a": cand(["1"])})["status"] == "single_candidate"
    assert same_edition({"a": cand(["1"]), "b": cand([])})["status"] == "unknown"
    assert same_edition({"a": cand(["1", "2"]), "b": cand(["2"])})["status"] == "match"
    assert same_edition({"a": cand(["1"]), "b": cand(["2"])})["status"] == "no_isbn_overlap"


# --- manifest & script --------------------------------------------------------

def test_merge_keeps_user_decision(tmp_path):
    path = tmp_path / "manifest.yaml"
    manifest = merge_title(load_manifest(path), "book", {"a.pdf": {}}, {"file": "a.pdf"}, "2026-09-19 10:00:00")
    manifest["titles"]["book"]["decision"] = {"file": "a.pdf", "extraction": "pdf_text_layer", "notes": "ok"}
    save_manifest(path, manifest)

    reloaded = merge_title(load_manifest(path), "book", {"a.pdf": {}, "b.epub": {}}, {"file": "b.epub"},
                           "2026-09-20 10:00:00")
    entry = reloaded["titles"]["book"]
    assert entry["decision"]["notes"] == "ok"
    assert entry["recommendation"]["file"] == "b.epub"
    assert set(entry["candidates"]) == {"a.pdf", "b.epub"}


def test_script_reports_by_default_and_writes_with_flag(tmp_path, monkeypatch):
    import audit_sources

    book = tmp_path / "candidates" / "book"
    book.mkdir(parents=True)
    make_pdf(book / "book.pdf")
    make_epub(book / "book.epub")
    manifest = tmp_path / "manifest.yaml"
    base = ["audit_sources.py", "--candidates", str(tmp_path / "candidates"), "--manifest", str(manifest)]

    monkeypatch.setattr(sys, "argv", base)
    audit_sources.main()
    assert not manifest.exists()

    monkeypatch.setattr(sys, "argv", base + ["--write"])
    audit_sources.main()
    data = yaml.safe_load(manifest.read_text())
    assert data["titles"]["book"]["recommendation"]["file"] == "book.epub"
    assert data["titles"]["book"]["decision"]["file"] is None


def test_script_rejects_unknown_book(tmp_path, monkeypatch):
    import audit_sources

    (tmp_path / "candidates").mkdir()
    monkeypatch.setattr(sys, "argv", ["audit_sources.py", "--candidates", str(tmp_path / "candidates"),
                                      "--book", "nope"])
    with pytest.raises(SystemExit):
        audit_sources.main()
