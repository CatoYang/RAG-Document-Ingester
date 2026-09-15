#!/usr/bin/env python
"""Minimal retrieval smoke test for the indexing pipeline (TODO.md Path 1.5).

Not a chat interface - just enough to see whether retrieval works at all:
embeds a question with the configured embedder, searches the configured
vector store, and prints the top matches with their source file and page.
A real chat/RAG interface (Path 5) builds on top of this, not instead of it.

Usage:
    python query.py config/<profile>.yaml "your question here" [--top-k 5]
"""
import argparse
import asyncio

from rich.console import Console
from rich.table import Table

from src.index.pipeline import IndexingPipeline

console = Console()


async def run(config_path: str, question: str, top_k: int) -> None:
    pipeline = IndexingPipeline()
    await pipeline.initialize(config_path)

    console.print(f"[dim]Embedding query with {pipeline.embedder.__class__.__name__}...[/dim]")
    embeddings = await pipeline.embedder.embed([question])

    console.print(f"[dim]Searching {pipeline.vectorstore.__class__.__name__} (top {top_k})...[/dim]")
    results = await pipeline.vectorstore.search(embeddings[0], top_k=top_k)

    if not results:
        console.print("[yellow]No results. Has anything been indexed into this vector store yet?[/yellow]")
        return

    table = Table(title=f'Results for: "{question}"')
    table.add_column("#", justify="right")
    table.add_column("Score")
    table.add_column("Source")
    table.add_column("Page")
    table.add_column("Section")
    table.add_column("Text")

    for i, r in enumerate(results, start=1):
        meta = r.metadata
        source = meta.get("filename") or meta.get("source") or "?"
        page = str(meta.get("page_number", "")) or "-"
        section = str(meta.get("section", "")) or "-"
        snippet = r.text[:200].replace("\n", " ")
        if len(r.text) > 200:
            snippet += "..."
        table.add_row(str(i), f"{r.score:.4f}", source, page, section, snippet)

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Query the indexed vector store (Path 1.5 retrieval smoke test)")
    parser.add_argument("config", help="Path to the YAML config file (must use the same indexing.* block the index was built with)")
    parser.add_argument("question", help="The question to search for")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return (default: 5)")
    args = parser.parse_args()

    asyncio.run(run(args.config, args.question, args.top_k))


if __name__ == "__main__":
    main()
