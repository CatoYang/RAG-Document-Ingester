#!/usr/bin/env python
"""Find near-duplicate/family clusters among already-extracted documents
(TODO.md Path 2: Semantic Deduplication + Document Family & Version
Clustering).

Runs MinHash-based near-duplicate detection (src/dedup/family.py) over every
markdown file in io.directories.output, reports the families it finds, and -
only with --apply - routes each family:

  --routing supersession   move every non-canonical member to a sibling
                            `superseded/` directory next to the output dir
                            (a move, not a delete: reversible, and both
                            pipelines only ever look at what's actually in
                            the output directory, so this is enough to drop
                            superseded files from future indexing runs).
  --routing temporal       tag every family member's frontmatter with
                            family_id/family_role instead of moving anything,
                            so all versions stay indexed with provenance -
                            MarkdownChunker/the vector stores already thread
                            arbitrary frontmatter keys through into stored
                            chunk metadata, so no other code needs to change.

Dry-run (no --apply) only reads files and prints a report - it never
modifies anything. The canonical pick shown is a heuristic (longest
extracted content wins, as a proxy for "most complete version") - eyeball it
before trusting --routing supersession to discard the right file.

Usage:
    python find_document_families.py config/<profile>.yaml
    python find_document_families.py config/<profile>.yaml --apply --routing supersession
    python find_document_families.py config/<profile>.yaml --apply --routing temporal --threshold 0.9
"""
import argparse
import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from rich.console import Console
from rich.table import Table

from src.config.settings import load_config
from src.dedup.family import cluster_families, minhash_signature, pick_canonical, shingle
from src.index.pipeline import IndexingPipeline

console = Console()


async def load_documents(output_dir: Path) -> Dict[str, str]:
    pipeline = IndexingPipeline()
    documents = {}
    for path in sorted(output_dir.glob("*.md")):
        doc = await pipeline.parse_document(str(path))
        documents[path.name] = doc.content
    return documents


def build_fingerprints(documents: Dict[str, str], shingle_size: int, num_perm: int):
    return {
        name: minhash_signature(shingle(text, shingle_size), num_perm=num_perm)
        for name, text in documents.items()
    }


def report_families(families: List[List[str]], documents: Dict[str, str]) -> List[List[str]]:
    multi = [members for members in families if len(members) > 1]

    table = Table(
        title=f"Document families ({len(multi)} with >1 member, "
              f"{len(families) - len(multi)} singletons)")
    table.add_column("#")
    table.add_column("Canonical (longest content)")
    table.add_column("Other members")

    for i, members in enumerate(multi, start=1):
        lengths = {m: len(documents[m]) for m in members}
        canonical = pick_canonical(members, lengths)
        others = ", ".join(m for m in members if m != canonical)
        table.add_row(str(i), canonical, others)

    console.print(table)
    return multi


def apply_supersession(families: List[List[str]], documents: Dict[str, str], output_dir: Path) -> None:
    superseded_dir = output_dir.parent / "superseded"
    superseded_dir.mkdir(parents=True, exist_ok=True)
    for members in families:
        lengths = {m: len(documents[m]) for m in members}
        canonical = pick_canonical(members, lengths)
        for member in members:
            if member == canonical:
                continue
            src = output_dir / member
            dst = superseded_dir / member
            shutil.move(str(src), str(dst))
            console.print(f"[yellow]Moved {member} -> {dst} (superseded by {canonical})[/yellow]")


def apply_temporal(families: List[List[str]], documents: Dict[str, str], output_dir: Path) -> None:
    for members in families:
        lengths = {m: len(documents[m]) for m in members}
        canonical = pick_canonical(members, lengths)
        family_id = str(uuid.uuid5(uuid.NAMESPACE_URL, canonical))
        for member in members:
            path = output_dir / member
            raw = path.read_text(encoding="utf-8")
            metadata, body = {}, raw
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    metadata = yaml.safe_load(parts[1]) or {}
                    body = parts[2].lstrip()
            metadata["family_id"] = family_id
            metadata["family_role"] = "canonical" if member == canonical else "variant"
            frontmatter = f"---\n{yaml.dump(metadata, sort_keys=False)}---\n\n"
            path.write_text(frontmatter + body, encoding="utf-8")
            console.print(f"[green]Tagged {member} as {metadata['family_role']} of family {family_id}[/green]")


async def run(config_path: str, threshold_override: Optional[float], apply: bool, routing: Optional[str]) -> None:
    config = load_config(config_path)
    output_dir = Path(config.io.directories.output)
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir

    if not output_dir.is_dir():
        console.print(f"[red]Output directory not found: {output_dir}[/red]")
        return

    fc_settings = config.pipeline.family_clustering
    threshold = threshold_override if threshold_override is not None else fc_settings.threshold

    documents = await load_documents(output_dir)
    if not documents:
        console.print(f"[yellow]No markdown files found in {output_dir}.[/yellow]")
        return

    console.print(
        f"[dim]Fingerprinting {len(documents)} documents "
        f"(shingle={fc_settings.shingle_size}, num_perm={fc_settings.num_perm}, "
        f"threshold={threshold})...[/dim]")
    fingerprints = build_fingerprints(documents, fc_settings.shingle_size, fc_settings.num_perm)
    families = cluster_families(fingerprints, threshold)

    multi = report_families(families, documents)

    if not multi:
        console.print("[dim]No families with more than one member found - nothing to route.[/dim]")
        return

    if apply:
        if routing == "supersession":
            apply_supersession(multi, documents, output_dir)
        elif routing == "temporal":
            apply_temporal(multi, documents, output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Find near-duplicate/family document clusters (TODO.md Path 2)")
    parser.add_argument("config", help="Path to the YAML config file")
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Override pipeline.family_clustering.threshold (estimated Jaccard similarity, 0-1)")
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually route families instead of just reporting them")
    parser.add_argument(
        "--routing", choices=["supersession", "temporal"], default=None,
        help="Required with --apply")
    args = parser.parse_args()

    if args.apply and not args.routing:
        parser.error("--apply requires --routing {supersession,temporal}")

    asyncio.run(run(args.config, args.threshold, args.apply, args.routing))


if __name__ == "__main__":
    main()
