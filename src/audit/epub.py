"""EPUB candidate measurements (TODO.md Path T1: Source Audit).

An EPUB is a zip of XHTML, so this reads the package (OPF), navigation and
every spine document straight out of the archive - no extraction library,
and nothing written to disk. As in `src/audit/pdf.py`, provenance calls are
heuristics returned with their evidence.
"""
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from src.audit.filename import find_isbns

_NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "enc": "http://www.w3.org/2001/04/xmlenc#",
}
# Font obfuscation is not DRM: it only scrambles embedded fonts.
_FONT_OBFUSCATION = ("http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC")
_TEX_ALT_RE = re.compile(r"\$|\\\(|\\\[|\\begin\{|\\[a-zA-Z]+")
# Checked against the image filename (e.g. Springer's `_Equ3_HTML.png`, `_TeX_IEq12.png`)
# and the classes of the image and its three nearest ancestors.
_EQUATION_SRC_RE = re.compile(r"_tex_|(?<![a-z])i?equ?\d|math|formula", re.IGNORECASE)
_EQUATION_CLASS_RE = re.compile(r"equation|math|formula", re.IGNORECASE)
_BACK_MATTER_RE = re.compile(r"index|glossary|back_?matter|answers|solutions|bibliograph", re.IGNORECASE)
_CONVERTER_RE = re.compile(r"calibre|ebook-convert|pdf2epub|abbyy|finereader", re.IGNORECASE)


def _read_xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(archive.read(name))


def _soup(archive: zipfile.ZipFile, name: str) -> BeautifulSoup:
    return BeautifulSoup(archive.read(name), "html.parser")


def _list_depth(ol: Tag) -> int:
    child_depths = [_list_depth(sub) for li in ol.find_all("li", recursive=False)
                    for sub in li.find_all("ol", recursive=False)]
    return 1 + max(child_depths, default=0)


def _nav_summary(archive: zipfile.ZipFile, nav_path: Optional[str], ncx_path: Optional[str]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"toc_entries": 0, "toc_depth": 0, "page_list_entries": 0, "source": None}
    if nav_path and nav_path in archive.namelist():
        soup = _soup(archive, nav_path)
        for nav in soup.find_all("nav"):
            kind = nav.get("epub:type", "")
            ol = nav.find("ol")
            if ol is None:
                continue
            if "toc" in kind.split():
                summary["toc_entries"] = len(ol.find_all("li"))
                summary["toc_depth"] = _list_depth(ol)
            elif "page-list" in kind.split():
                summary["page_list_entries"] = len(ol.find_all("li"))
        summary["source"] = "nav"
    elif ncx_path and ncx_path in archive.namelist():
        root = _read_xml(archive, ncx_path)
        points = root.findall(".//{*}navPoint")
        summary["toc_entries"] = len(points)

        def depth(el: ET.Element) -> int:
            return 1 + max((depth(c) for c in el.findall("{*}navPoint")), default=0)

        nav_map = root.find("{*}navMap")
        summary["toc_depth"] = max((depth(p) for p in nav_map.findall("{*}navPoint")), default=0) \
            if nav_map is not None else 0
        summary["page_list_entries"] = len(root.findall(".//{*}pageTarget"))
        summary["source"] = "ncx"
    return summary


def _drm(archive: zipfile.ZipFile) -> Dict[str, Any]:
    names = set(archive.namelist())
    if "META-INF/rights.xml" in names:
        return {"drm": True, "drm_evidence": "META-INF/rights.xml present (Adobe ADEPT)"}
    if "META-INF/encryption.xml" not in names:
        return {"drm": False, "drm_evidence": "no encryption.xml"}
    root = _read_xml(archive, "META-INF/encryption.xml")
    encrypted = []
    for data in root.findall(".//enc:EncryptedData", _NS):
        method = data.find("enc:EncryptionMethod", _NS)
        algorithm = method.get("Algorithm", "") if method is not None else ""
        ref = data.find(".//enc:CipherReference", _NS)
        uri = ref.get("URI", "") if ref is not None else ""
        if algorithm not in _FONT_OBFUSCATION:
            encrypted.append(uri)
    if encrypted:
        return {"drm": True, "drm_evidence": f"{len(encrypted)} encrypted resources, e.g. {encrypted[0]}"}
    return {"drm": False, "drm_evidence": "encryption.xml only obfuscates fonts"}


def _content_stats(soup: BeautifulSoup) -> Dict[str, int]:
    stats = {f"h{n}": len(soup.find_all(f"h{n}")) for n in range(1, 7)}
    stats["mathml"] = len(soup.find_all(re.compile(r"^(m:)?math$")))
    stats["tables"] = len(soup.find_all("table"))
    stats["figures"] = len({id(t) for t in soup.find_all("figure")} | {
        id(t) for t in soup.find_all(class_=re.compile(r"^figure$", re.IGNORECASE))})
    stats["page_breaks"] = len(soup.find_all(
        lambda t: "pagebreak" in t.get("epub:type", "") or t.get("role") == "doc-pagebreak"))
    stats["text_chars"] = len(soup.get_text(" ", strip=True))

    images = soup.find_all("img")
    stats["images"] = len(images)
    tex_alt = equation_images = equation_images_no_source = 0
    for img in images:
        alt = img.get("alt", "") or ""
        has_tex = bool(_TEX_ALT_RE.search(alt))
        nearby = [img, *list(img.parents)[:3]]
        classes = " ".join(" ".join(t.get("class", [])) for t in nearby if isinstance(t, Tag))
        is_equation = has_tex or bool(_EQUATION_SRC_RE.search(posixpath.basename(img.get("src", "")))) \
            or bool(_EQUATION_CLASS_RE.search(classes))
        tex_alt += has_tex
        equation_images += is_equation
        equation_images_no_source += is_equation and not has_tex
    stats["tex_alt_images"] = tex_alt
    stats["equation_images"] = equation_images
    stats["equation_images_no_source"] = equation_images_no_source
    return stats


def _maths_mode(totals: Dict[str, int]) -> Dict[str, Any]:
    if totals["mathml"]:
        mode = "mathml"
    elif totals["tex_alt_images"]:
        mode = "latex_alt_text"
    elif totals["equation_images"]:
        mode = "images_no_source"
    else:
        mode = "none_detected"
    coverage = (totals["tex_alt_images"] / totals["equation_images"]) if totals["equation_images"] else None
    return {
        "mode": mode,
        "mathml_elements": totals["mathml"],
        "equation_images": totals["equation_images"],
        "tex_alt_images": totals["tex_alt_images"],
        "latex_alt_coverage": round(coverage, 3) if coverage is not None else None,
    }


def audit_epub(path: str) -> Dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        container = _read_xml(archive, "META-INF/container.xml")
        rootfile = container.find(".//c:rootfile", _NS)
        opf_path = rootfile.get("full-path")
        opf_dir = posixpath.dirname(opf_path)
        opf_raw = archive.read(opf_path).decode("utf-8", errors="replace")
        opf = ET.fromstring(opf_raw.encode("utf-8"))
        metadata = opf.find("opf:metadata", _NS)

        def dc(tag: str) -> List[str]:
            return [el.text.strip() for el in metadata.findall(f"dc:{tag}", _NS) if el.text]

        metas = metadata.findall("opf:meta", _NS)
        layout = next((m.text.strip() for m in metas
                       if m.get("property") == "rendition:layout" and m.text), "reflowable")
        generators = [m.get("content") for m in metas if m.get("name") == "generator" and m.get("content")]
        generators += [c.strip() for c in re.findall(r"<!--(.*?)-->", opf_raw, re.DOTALL)
                       if re.search(r"convert|generat|creat", c, re.IGNORECASE)]
        calibre_meta = any((m.get("name") or "").startswith("calibre:") for m in metas)

        evidence: List[str] = []
        converter = _CONVERTER_RE.search(" ".join(generators) + opf_raw[:5000])
        if calibre_meta or converter:
            origin = "converted"
            evidence.append(f"conversion tool in package metadata: {converter.group(0) if converter else 'calibre:'}")
        elif generators or dc("publisher"):
            origin = "publisher"
            evidence += [f"generator: {g}" for g in generators] or [f"publisher: {dc('publisher')[0]}"]
        else:
            origin = "unknown"
            evidence.append("no generator or publisher metadata")

        def resolve(href: str) -> str:
            return posixpath.normpath(posixpath.join(opf_dir, href))

        items = {item.get("id"): item for item in opf.find("opf:manifest", _NS)}
        nav_item = next((i for i in items.values() if "nav" in (i.get("properties") or "").split()), None)
        ncx_item = next((i for i in items.values() if i.get("media-type") == "application/x-dtbncx+xml"), None)
        nav = _nav_summary(archive,
                           resolve(nav_item.get("href")) if nav_item is not None else None,
                           resolve(ncx_item.get("href")) if ncx_item is not None else None)

        spine = opf.find("opf:spine", _NS)
        documents = []
        totals: Dict[str, int] = {}
        for itemref in spine.findall("opf:itemref", _NS):
            item = items.get(itemref.get("idref"))
            if item is None:
                continue
            href = resolve(item.get("href"))
            if href not in archive.namelist():
                continue
            stats = _content_stats(_soup(archive, href))
            for key, value in stats.items():
                totals[key] = totals.get(key, 0) + value
            documents.append({"href": href, "linear": itemref.get("linear", "yes") != "no", **stats})

        linear_docs = [d for d in documents if d["linear"] and d["text_chars"] > 0]
        docs_with_headings = [d for d in linear_docs if d["h1"] + d["h2"] + d["h3"] > 0]

        return {
            "format": "epub",
            "epub_version": opf.get("version"),
            "title": (dc("title") or [None])[0],
            "creators": dc("creator"),
            "publisher": (dc("publisher") or [None])[0],
            "origin": origin,
            "evidence": evidence,
            **_drm(archive),
            "layout": "fixed" if layout == "pre-paginated" else "reflowable",
            "text": {"chars": totals.get("text_chars", 0)},
            "structure": {
                "spine_documents": len(documents),
                "linear_documents_with_text": len(linear_docs),
                "documents_with_headings": len(docs_with_headings),
                "headings": {f"h{n}": totals.get(f"h{n}", 0) for n in range(1, 7)},
                "toc_entries": nav["toc_entries"],
                "toc_depth": nav["toc_depth"],
                "nav_source": nav["source"],
            },
            "page_citations": {
                "page_list_entries": nav["page_list_entries"],
                "page_break_markers": totals.get("page_breaks", 0),
            },
            "maths": _maths_mode(totals),
            "figures": totals.get("figures", 0),
            "tables": totals.get("tables", 0),
            "back_matter": [d["href"] for d in documents if _BACK_MATTER_RE.search(posixpath.basename(d["href"]))],
            # Only identifiers that claim to be ISBNs, so UUID identifiers
            # can't produce accidental matches.
            "isbns": find_isbns(" ".join(
                i for i in dc("identifier") if "isbn" in i.lower() or re.fullmatch(r"[\dXx\s-]+", i))),
        }
