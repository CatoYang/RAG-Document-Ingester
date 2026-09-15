#!/usr/bin/env python
"""Golden Q&A recall harness (TODO.md Path 1.5 / Path 2).

Reads a YAML file of hand-written questions with known-correct source
book/page (see eval/golden_qa.example.yaml for the format), runs each
through the same retrieval path as query.py, and reports top-k recall: how
often the expected source file (and, if given, a nearby page) actually shows
up in the results.

This is meant to be the yardstick every retrieval-quality change (hybrid
search, reranking, chunking tweaks - TODO.md Path 2) gets measured against.
Re-run it before and after a change; a change that doesn't move this number
probably isn't worth keeping.

IMPORTANT: eval/golden_qa.example.yaml ships with placeholder questions, not
real answers. Real questions have to come from someone who actually knows
the books - don't fabricate expected_source/expected_page values, or the
recall number this produces is meaningless.

Usage:
    python eval_golden.py config/<profile>.yaml eval/golden_qa.yaml [--top-k 5]
"""
import argparse
import asyncio

import yaml
from rich.console import Console
from rich.table import Table

from src.index.pipeline import IndexingPipeline

console = Console()


async def run(config_path: str, qa_path: str, top_k: int, page_tolerance: int) -> None:
    with open(qa_path, "r", encoding="utf-8") as f:
        qa_set = yaml.safe_load(f) or {}

    questions = qa_set.get("questions", [])
    if not questions:
        console.print(f"[yellow]No questions found in {qa_path}.[/yellow]")
        return

    pipeline = IndexingPipeline()
    await pipeline.initialize(config_path)

    table = Table(title=f"Golden Q&A recall @ top-{top_k}")
    table.add_column("Hit")
    table.add_column("Question")
    table.add_column("Expected")
    table.add_column("Best match")

    hits = 0
    for qa in questions:
        question = qa["question"]
        expected_source = qa.get("expected_source")
        expected_page = qa.get("expected_page")

        embeddings = await pipeline.embedder.embed([question])
        results = await pipeline.vectorstore.search(embeddings[0], top_k=top_k)

        hit = False
        best_match = "-"
        for r in results:
            source = r.metadata.get("filename")
            page = r.metadata.get("page_number")
            page_matches = expected_page is None or page is None or abs(page - expected_page) <= page_tolerance
            if source == expected_source and page_matches:
                hit = True
                best_match = f"{source} (p.{page})"
                break

        if hit:
            hits += 1
        elif results:
            top = results[0]
            best_match = f"{top.metadata.get('filename')} (p.{top.metadata.get('page_number')})"

        table.add_row(
            "✅" if hit else "❌",
            question[:60],
            f"{expected_source} (p.{expected_page})",
            best_match,
        )

    console.print(table)
    console.print(f"\n[bold]Recall@{top_k}: {hits}/{len(questions)} ({100 * hits / len(questions):.0f}%)[/bold]")


def main():
    parser = argparse.ArgumentParser(description="Golden Q&A recall harness (Path 1.5 / Path 2)")
    parser.add_argument("config", help="Path to the YAML config file")
    parser.add_argument("qa_file", help="Path to a golden Q&A YAML file (see eval/golden_qa.example.yaml)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--page-tolerance", type=int, default=2,
                         help="A hit counts if the returned page is within this many pages of expected_page")
    args = parser.parse_args()

    asyncio.run(run(args.config, args.qa_file, args.top_k, args.page_tolerance))


if __name__ == "__main__":
    main()
