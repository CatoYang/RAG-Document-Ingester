"""PDF candidate measurements (TODO.md Path T1: Source Audit).

Everything here is CPU-only PyMuPDF work over an evenly spaced sample of
pages, so a 600-page textbook audits in seconds. The origin/provenance
calls are heuristics: each one is returned with the evidence it was based
on, for a human to check.
"""
import re
from collections import Counter
from typing import Any, Dict, List, Optional

import pymupdf

from src.audit.filename import find_isbns

# Producer/Creator substrings, checked in this order.
_SCAN_TOOLS = ("abbyy", "finereader", "tesseract", "internet archive", "luratech",
               "scansnap", "paper capture", "omnipage", "readiris", "kofax", "djvu")
_CONVERTERS = ("calibre", "ebook-convert", "wkhtmltopdf")
_TYPESETTERS = ("indesign", "distiller", "pdftex", "xetex", "luatex", "latex", "antenna house",
                "arbortext", "3b2", "quarkxpress", "xep", "prince", "framemaker")

# Subset prefix ("ABCDEF+") is stripped before matching.
_LATEX_FONT_RE = re.compile(r"^(CM[A-Z]{1,4}\d+|LM[A-Z]|SFRM|SFBX|MSAM|MSBM)")
_MATH_FONT_RE = re.compile(
    r"^(CMMI|CMSY|CMEX|MSAM|MSBM|LMMath|STIXMath|STIXGeneral|Cambria ?Math|MathematicalPi|"
    r"MTMI|MTSY|MTEX|Euclid|TeXGyre\w*Math|rsfs|eufm)", re.IGNORECASE)
_LIGATURES_RE = re.compile("[ﬀ-ﬆ]")
_BACK_MATTER_RE = re.compile(
    r"^(index|glossary|bibliography|references|answers?\b|solutions?\b|answer key)", re.IGNORECASE)

SCAN_PAGE_IMAGE_COVERAGE = 0.8   # an image covering this much of a page counts as a page scan
SCAN_PAGE_SHARE = 0.5            # ...and this share of sampled pages makes the file a scan
MIN_CHARS_PER_PAGE = 100.0       # same threshold as AutoPdfExtractor (src/extract/pdf_density.py)


def _sample_indices(page_count: int, sample_size: int) -> List[int]:
    if page_count <= sample_size:
        return list(range(page_count))
    step = page_count / sample_size
    return sorted({int(i * step) for i in range(sample_size)})


def _base_font(name: str) -> str:
    return name.split("+", 1)[1] if "+" in name else name


def _printed_page_number(lines: List[str], page_count: int) -> Optional[int]:
    """A bare integer among a page's first/last three lines, i.e. a running
    head or footer page number."""
    for line in lines[:3] + lines[-3:]:
        if line.isdigit() and 0 < int(line) <= page_count:
            return int(line)
    return None


def _classify_origin(producer_text: str, full_page_image_share: float, avg_chars: float,
                     latex_font_share: float) -> Dict[str, Any]:
    evidence: List[str] = []
    if full_page_image_share >= SCAN_PAGE_SHARE:
        evidence.append(f"{full_page_image_share:.0%} of sampled pages are a full-page image")
        origin = "scan_ocr" if avg_chars >= MIN_CHARS_PER_PAGE else "scan_image_only"
        if origin == "scan_ocr":
            evidence.append("text layer over page images (embedded OCR)")
        return {"origin": origin, "evidence": evidence}

    lowered = producer_text.lower()
    for tool in _SCAN_TOOLS:
        if tool in lowered:
            evidence.append(f"producer/creator mentions '{tool}'")
            return {"origin": "scan_ocr", "evidence": evidence}
    for tool in _CONVERTERS:
        if tool in lowered:
            evidence.append(f"producer/creator mentions '{tool}' (page numbers won't match print)")
            return {"origin": "converted", "evidence": evidence}
    for tool in _TYPESETTERS:
        if tool in lowered:
            evidence.append(f"producer/creator mentions '{tool}'")
            return {"origin": "typeset", "evidence": evidence}
    if latex_font_share >= 0.5:
        evidence.append(f"LaTeX (Computer/Latin Modern) fonts on {latex_font_share:.0%} of sampled pages")
        if not producer_text.strip():
            evidence.append("producer/creator metadata is empty (stripped)")
        return {"origin": "typeset", "evidence": evidence}

    evidence.append("no recognised producer/creator and no scan fingerprint")
    return {"origin": "unknown", "evidence": evidence}


def _back_matter(toc: List[List[Any]], page_count: int) -> List[Dict[str, Any]]:
    top = [entry for entry in toc if entry[0] == 1]
    sections = []
    for i, (_, title, start) in enumerate(entry[:3] for entry in top):
        if _BACK_MATTER_RE.match(title.strip()):
            end = top[i + 1][2] - 1 if i + 1 < len(top) else page_count
            sections.append({"title": title.strip(), "pages": [start, end]})
    return sections


def audit_pdf(path: str, sample_size: int = 40) -> Dict[str, Any]:
    doc = pymupdf.open(path)
    try:
        page_count = doc.page_count
        metadata = doc.metadata or {}
        producer_text = " ".join(filter(None, [metadata.get("producer"), metadata.get("creator")]))
        toc = doc.get_toc()
        indices = _sample_indices(page_count, sample_size)

        chars: List[int] = []
        image_only = full_page_image = latex_pages = math_pages = 0
        ligatures = hyphen_breaks = total_lines = 0
        offsets: Counter = Counter()
        for i in indices:
            page = doc[i]
            text = page.get_text()
            chars.append(len(text.strip()))
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            total_lines += len(lines)
            hyphen_breaks += sum(1 for line in lines if re.search(r"[a-z]-$", line))
            ligatures += len(_LIGATURES_RE.findall(text))

            area = page.rect.width * page.rect.height
            covered = any(
                pymupdf.Rect(info["bbox"]).get_area() >= SCAN_PAGE_IMAGE_COVERAGE * area
                for info in page.get_image_info())
            full_page_image += covered
            image_only += covered and len(text.strip()) < MIN_CHARS_PER_PAGE

            fonts = [_base_font(f[3]) for f in page.get_fonts()]
            latex_pages += any(_LATEX_FONT_RE.match(f) for f in fonts)
            math_pages += any(_MATH_FONT_RE.match(f) for f in fonts)

            printed = _printed_page_number(lines, page_count)
            if printed is not None:
                offsets[(i + 1) - printed] += 1

        sampled = max(len(indices), 1)
        avg_chars = sum(chars) / sampled
        full_page_share = full_page_image / sampled
        latex_share = latex_pages / sampled

        printed_pages: Dict[str, Any] = {"detected": False}
        if offsets:
            offset, hits = offsets.most_common(1)[0]
            agreement = hits / sampled
            printed_pages = {"detected": agreement >= 0.5, "offset": offset,
                             "agreement": round(agreement, 2)}

        isbn_text = "\n".join(
            line for i in range(min(12, page_count))
            for line in doc[i].get_text().splitlines() if "isbn" in line.lower())

        return {
            "format": "pdf",
            "pages": page_count,
            "encrypted": bool(doc.is_encrypted),
            "producer": metadata.get("producer") or None,
            "creator": metadata.get("creator") or None,
            **_classify_origin(producer_text, full_page_share, avg_chars, latex_share),
            "text": {
                "avg_chars_per_page": round(avg_chars),
                "has_text_layer": avg_chars >= MIN_CHARS_PER_PAGE,
                "image_only_page_share": round(image_only / sampled, 2),
                "ligature_chars": ligatures,
                "hyphenated_line_share": round(hyphen_breaks / max(total_lines, 1), 3),
            },
            "structure": {
                "toc_entries": len(toc),
                "toc_depth": max((entry[0] for entry in toc), default=0),
            },
            "page_citations": {
                "page_labels": any(doc[i].get_label() for i in indices),
                "printed_pages": printed_pages,
            },
            "maths": {
                "math_font_page_share": round(math_pages / sampled, 2),
                "latex_font_page_share": round(latex_share, 2),
                # A PDF text layer has no sub/superscript or fraction structure,
                # so any maths it contains comes out flattened.
                "mode": "flattened_text" if math_pages else "none_detected",
            },
            "back_matter": _back_matter(toc, page_count),
            "isbns": find_isbns(isbn_text),
            "sampled_pages": len(indices),
        }
    finally:
        doc.close()
