#!/usr/bin/env python
"""Audit candidate source files and recommend a format and extraction path
per title (TODO.md Path T1: Source Audit).

Expects one folder per title under the candidates root, holding every
downloaded candidate (PDF, EPUB, ...) for that title:

    data/raw/textbooks/_candidates/<book-slug>/<candidate files>

Measures each candidate (src/audit/pdf.py, src/audit/epub.py: CPU-only,
reads files, never modifies them), prints a report and a recommendation
(src/audit/recommend.py). Only with --write does it update the manifest,
which keeps any `decision` already filled in for a title.

Usage:
    python audit_sources.py
    python audit_sources.py --book machine-learning-for-text
    python audit_sources.py --write
"""
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from rich.console import Console
from rich.table import Table

from src.audit.manifest import load_manifest, merge_title, save_manifest
from src.audit.recommend import audit_book, recommend

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CANDIDATES = PROJECT_ROOT / "data/raw/textbooks/_candidates"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/raw/textbooks/manifest.yaml"

console = Console()


def _pdf_row(m: Dict[str, Any]) -> list:
    printed = m["page_citations"]["printed_pages"]
    pages = f"printed (offset {printed['offset']})" if printed.get("detected") else "PDF page index only"
    return [
        m["origin"],
        f"{m['text']['avg_chars_per_page']} chars/page",
        f"TOC {m['structure']['toc_entries']} entries, depth {m['structure']['toc_depth']}",
        f"{m['maths']['mode']} ({m['maths']['math_font_page_share']:.0%} of pages)",
        pages,
    ]


def _epub_row(m: Dict[str, Any]) -> list:
    s, maths, pc = m["structure"], m["maths"], m["page_citations"]
    headings = ", ".join(f"{k} {v}" for k, v in s["headings"].items() if v)
    maths_note = maths["mode"]
    if maths["latex_alt_coverage"] is not None:
        maths_note += f" ({maths['tex_alt_images']}/{maths['equation_images']} images)"
    pages = f"page-list {pc['page_list_entries']}" if pc["page_list_entries"] else \
        f"{pc['page_break_markers']} page breaks" if pc["page_break_markers"] else "none"
    return [
        f"{m['origin']}, {m['layout']}, DRM {'yes' if m['drm'] else 'no'}",
        f"{m['text']['chars']:,} chars",
        f"{s['documents_with_headings']}/{s['linear_documents_with_text']} docs with headings; {headings}",
        maths_note,
        pages,
    ]


def report(slug: str, candidates: Dict[str, Any], recommendation: Dict[str, Any]) -> None:
    table = Table(title=slug, show_lines=True)
    for column in ("Candidate", "Origin", "Text", "Structure", "Maths", "Page citations"):
        table.add_column(column)
    for name, m in candidates.items():
        if not m.get("supported"):
            table.add_row(name, f"[red]unsupported .{m.get('format')}[/red]", m.get("error", ""), "", "", "")
            continue
        row = _pdf_row(m) if m["format"] == "pdf" else _epub_row(m)
        table.add_row(f"{name}\n{m['size_mb']} MB, md5 {m['md5'][:8]}", *row)
    console.print(table)

    edition = recommendation["same_edition"]
    console.print(f"Same edition: [bold]{edition['status']}[/bold] "
                  f"{edition.get('shared_isbns') or edition.get('note') or ''}")
    if recommendation["file"] is None:
        console.print("[bold red]No usable candidate.[/bold red]")
    else:
        console.print(f"[bold green]Recommend:[/bold green] {recommendation['file']} "
                      f"→ [bold]{recommendation['extraction']}[/bold]")
    for reason in recommendation["reasons"]:
        console.print(f"  + {reason}")
    for caveat in recommendation["caveats"]:
        console.print(f"  [yellow]! {caveat}[/yellow]")
    for name, reasons in {**recommendation.get("alternatives", {}), **recommendation["rejected"]}.items():
        console.print(f"  [dim]- {name}: {'; '.join(reasons)}[/dim]")
    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES,
                        help="folder holding one sub-folder of candidates per title")
    parser.add_argument("--book", action="append", help="only audit this title folder (repeatable)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write", action="store_true", help="update the manifest (default: report only)")
    args = parser.parse_args()

    if not args.candidates.is_dir():
        raise SystemExit(f"Candidates folder not found: {args.candidates}")
    book_dirs = sorted(p for p in args.candidates.iterdir() if p.is_dir())
    stray = sorted(p.name for p in args.candidates.iterdir() if p.is_file())
    if stray:
        console.print(f"[yellow]Skipping files not in a title folder: {stray}[/yellow]")
    if args.book:
        book_dirs = [p for p in book_dirs if p.name in set(args.book)]
        missing = set(args.book) - {p.name for p in book_dirs}
        if missing:
            raise SystemExit(f"No such title folder(s): {sorted(missing)}")

    manifest = load_manifest(args.manifest) if args.write else None
    audited_at = datetime.now().replace(microsecond=0).isoformat(" ")
    for book_dir in book_dirs:
        candidates = audit_book(book_dir)
        if not candidates:
            console.print(f"[yellow]{book_dir.name}: no files[/yellow]")
            continue
        recommendation = recommend(candidates)
        report(book_dir.name, candidates, recommendation)
        if manifest is not None:
            merge_title(manifest, book_dir.name, candidates, recommendation, audited_at)

    if manifest is not None:
        save_manifest(args.manifest, manifest)
        console.print(f"[green]Manifest updated: {args.manifest}[/green]")
    else:
        console.print("[dim]Report only; pass --write to update the manifest.[/dim]")


if __name__ == "__main__":
    main()
