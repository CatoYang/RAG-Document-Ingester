"""Per-title audit and format/extraction recommendation (TODO.md Path T1).

`audit_book` measures every candidate file for one title; `recommend` ranks
them by the rule in TODO.md. The recommendation is a suggestion with its
reasons: the user's `decision` in the manifest is what later stages use.
"""
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.audit.epub import audit_epub
from src.audit.filename import parse_archive_filename
from src.audit.pdf import audit_pdf

SUPPORTED_SUFFIXES = {".pdf": audit_pdf, ".epub": audit_epub}
MIN_HEADING_COVERAGE = 0.8       # share of text-bearing spine documents with an h1-h3
MAX_UNSOURCED_EQUATION_IMAGES = 20
MATHS_HEAVY_PAGE_SHARE = 0.2     # sampled PDF pages using a maths font

# Lower is better. Extraction path names are the ones recorded in the manifest.
_TIERS = {
    "epub_good": (1, "epub_structured"),
    "pdf_typeset": (2, "pdf_text_layer"),
    "pdf_converted": (3, "pdf_text_layer"),
    "epub_weak": (4, "epub_structured"),
    "pdf_scan_ocr": (5, "pdf_text_layer"),
    "pdf_image_only": (6, "pdf_ocr"),
}


def md5sum(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_candidate(path: Path) -> Dict[str, Any]:
    parsed = parse_archive_filename(path.name)
    md5 = md5sum(path)
    entry: Dict[str, Any] = {
        "md5": md5,
        "size_mb": round(path.stat().st_size / 1e6, 1),
        "filename_metadata": parsed,
        "md5_matches_filename": (md5 == parsed["md5"]) if parsed["md5"] else None,
    }
    auditor = SUPPORTED_SUFFIXES.get(path.suffix.lower())
    if auditor is None:
        entry.update({"format": path.suffix.lower().lstrip("."), "supported": False})
        return entry
    try:
        entry.update({"supported": True, **auditor(str(path))})
    except Exception as exc:  # a corrupt file is an audit finding, not a crash
        entry.update({"format": path.suffix.lower().lstrip("."), "supported": False,
                      "error": f"{type(exc).__name__}: {exc}"})
    return entry


def audit_book(book_dir: Path) -> Dict[str, Dict[str, Any]]:
    return {path.name: audit_candidate(path)
            for path in sorted(book_dir.iterdir()) if path.is_file() and not path.name.startswith(".")}


def _classify(metrics: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    """(tier key or None if unusable, reasons)."""
    if not metrics.get("supported"):
        return None, [metrics.get("error") or f"no extractor for .{metrics.get('format')} files"]

    if metrics["format"] == "epub":
        if metrics["drm"]:
            return None, [f"DRM: {metrics['drm_evidence']}"]
        if metrics["layout"] == "fixed":
            return None, ["fixed-layout EPUB: positioned pages, no reflowable structure"]
        structure = metrics["structure"]
        coverage = structure["documents_with_headings"] / max(structure["linear_documents_with_text"], 1)
        problems = []
        if metrics["origin"] == "converted":
            problems.append("converted EPUB (" + "; ".join(metrics["evidence"]) + ")")
        if coverage < MIN_HEADING_COVERAGE:
            problems.append(f"only {coverage:.0%} of content documents have real h1-h3 headings")
        unsourced = metrics["maths"]["equation_images"] - metrics["maths"]["tex_alt_images"]
        if metrics["maths"]["mode"] == "images_no_source" and unsourced > MAX_UNSOURCED_EQUATION_IMAGES:
            problems.append(f"{unsourced} equation images with no LaTeX/MathML source")
        if problems:
            return "epub_weak", problems
        return "epub_good", [f"reflowable {metrics['origin']} EPUB, headings in {coverage:.0%} of content documents",
                             f"maths: {metrics['maths']['mode']}"]

    if metrics["encrypted"]:
        return None, ["PDF is encrypted"]
    origin = metrics["origin"]
    if origin == "scan_image_only" or not metrics["text"]["has_text_layer"]:
        return "pdf_image_only", ["no usable text layer: needs Marker/OCR"]
    if origin == "scan_ocr":
        return "pdf_scan_ocr", ["scan with embedded OCR of unknown quality"]
    if origin == "converted":
        return "pdf_converted", ["converted PDF: page numbers won't match print"]
    return "pdf_typeset", [f"{origin} PDF with a text layer ({metrics['text']['avg_chars_per_page']} chars/page)"]


def _caveats(chosen: Dict[str, Any], candidates: Dict[str, Dict[str, Any]]) -> List[str]:
    caveats = []
    if chosen["format"] == "epub":
        maths = chosen["maths"]
        if maths["latex_alt_coverage"] is not None and maths["latex_alt_coverage"] < 1:
            missing = maths["equation_images"] - maths["tex_alt_images"]
            caveats.append(f"{missing} equation images have no LaTeX alt text and will be lost")
        if not chosen["page_citations"]["page_list_entries"] and not chosen["page_citations"]["page_break_markers"]:
            printed = [name for name, m in candidates.items() if m.get("format") == "pdf" and m.get("supported")
                       and m["page_citations"]["printed_pages"].get("detected")]
            hint = f"; {printed[0]} has printed page numbers and could supply a page map" if printed else ""
            caveats.append("EPUB has no page-list or page-break markers: no page citations" + hint)
    else:
        if chosen["maths"]["math_font_page_share"] >= MATHS_HEAVY_PAGE_SHARE:
            caveats.append(f"maths on {chosen['maths']['math_font_page_share']:.0%} of sampled pages "
                           "will be flattened (sub/superscripts, fractions lost)")
        if chosen["text"]["ligature_chars"]:
            caveats.append("text layer uses ligature characters (fi/fl/ff): normalise during cleaning")
        if chosen["text"]["hyphenated_line_share"] > 0.02:
            caveats.append("words hyphenated across line breaks: rejoin during cleaning")
    if chosen.get("back_matter"):
        caveats.append(f"back matter to strip or separate: {chosen['back_matter']}")
    return caveats


def same_edition(candidates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Whether the candidates share an ISBN. Print and eBook ISBNs differ, so
    no overlap means "check by hand", not "different edition"."""
    isbn_sets = {name: set(m.get("isbns") or []) | set(m["filename_metadata"]["isbns"])
                 for name, m in candidates.items()}
    known = {name: s for name, s in isbn_sets.items() if s}
    if len(candidates) < 2:
        return {"status": "single_candidate"}
    if len(known) < 2:
        return {"status": "unknown", "note": "fewer than two candidates have an ISBN"}
    shared = set.intersection(*known.values())
    if shared:
        return {"status": "match", "shared_isbns": sorted(shared)}
    return {"status": "no_isbn_overlap", "note": "could still be print vs. eBook ISBN; check the copyright page"}


def recommend(candidates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ranked = []
    rejected = {}
    for name, metrics in candidates.items():
        tier, reasons = _classify(metrics)
        if tier is None:
            rejected[name] = reasons
        else:
            ranked.append((_TIERS[tier][0], name, tier, reasons))
    ranked.sort()

    result: Dict[str, Any] = {"same_edition": same_edition(candidates)}
    if not ranked:
        result.update({"file": None, "extraction": None, "reasons": ["no usable candidate"],
                       "caveats": [], "rejected": rejected})
        return result

    _, name, tier, reasons = ranked[0]
    caveats = _caveats(candidates[name], candidates)
    if tier == "pdf_image_only":
        caveats.insert(0, "OCR is GPU-heavy on this machine: confirm the book is worth it before running Marker")
    result.update({
        "file": name,
        "extraction": _TIERS[tier][1],
        "reasons": reasons,
        "caveats": caveats,
        "alternatives": {other: other_reasons for _, other, _, other_reasons in ranked[1:]},
        "rejected": rejected,
    })
    return result
