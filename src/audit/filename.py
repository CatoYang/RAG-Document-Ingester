"""Parse Anna's Archive download filenames (TODO.md Path T1: Source Audit).

Downloads are usually named
`Title -- Author -- Edition, Year -- Publisher -- ISBN, ISBN -- md5 -- Anna's Archive.ext`,
but fields go missing or shift between records, so each field is classified
by what it looks like (md5, ISBN, year) rather than by position - apart from
title and author, which are always the first two.
"""
import re
from pathlib import Path
from typing import Any, Dict, List

_SEPARATOR = " -- "
_ARCHIVE_SUFFIX_RE = re.compile(r"^anna[’'`]?s archive$", re.IGNORECASE)
_MD5_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
_ISBN_RE = re.compile(r"\b(97[89]\d{10}|\d{9}[\dX])\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


def normalise_isbn(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw).upper()


def find_isbns(text: str) -> List[str]:
    """ISBN-10/13s in `text`, hyphens/spaces removed, in first-seen order."""
    compact = re.sub(r"(?<=\d)[\s-](?=[\dXx])", "", text)
    seen: List[str] = []
    for match in _ISBN_RE.findall(compact):
        isbn = match.upper()
        if isbn not in seen:
            seen.append(isbn)
    return seen


def parse_archive_filename(filename: str) -> Dict[str, Any]:
    """Split an Anna's Archive filename into metadata fields. A name without
    the ` -- ` separators (e.g. one the user already renamed) comes back as
    just a title, with `is_archive_name` False."""
    stem = Path(filename).stem
    fields = [f.strip() for f in stem.split(_SEPARATOR)]

    result: Dict[str, Any] = {
        "is_archive_name": False,
        "title": stem.strip(),
        "authors": None,
        "year": None,
        "isbns": [],
        "md5": None,
        "other": [],
    }
    if len(fields) < 2:
        return result

    if _ARCHIVE_SUFFIX_RE.match(fields[-1]):
        fields = fields[:-1]
        result["is_archive_name"] = True

    result["title"] = fields[0]
    result["authors"] = fields[1] if len(fields) > 1 else None

    for field in fields[2:]:
        if _MD5_RE.match(field):
            result["md5"] = field.lower()
            result["is_archive_name"] = True
            continue
        isbns = find_isbns(field)
        # An ISBN field is only ISBNs, commas and whitespace; anything else
        # (e.g. "2nd ed., 2022") is an edition/publisher field.
        if isbns and not re.sub(r"[\dXx,;\s-]", "", field):
            result["isbns"].extend(i for i in isbns if i not in result["isbns"])
            continue
        year = _YEAR_RE.search(field)
        if year and result["year"] is None:
            result["year"] = int(year.group(1))
        result["other"].append(field)

    return result
