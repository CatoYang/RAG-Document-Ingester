import argparse
import asyncio
import sys
from dotenv import load_dotenv
from rich.console import Console
from pathlib import Path

from src.pipeline import IngestionPipeline
from src.index.pipeline import IndexingPipeline
from src.config.settings import load_config

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
console = Console()

async def async_main():
    parser = argparse.ArgumentParser(description="Enterprise Document Ingestion Pipeline for RAG")
    parser.add_argument(
        "config", 
        type=str, 
        nargs="?", 
        default="config/config.yaml",
        help="Path to the YAML configuration file (default: config/config.yaml)"
    )
    parser.add_argument("--file", type=str, help="Process a specific file")

    args = parser.parse_args()
    
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/bold red]")
        sys.exit(1)

    console.print(f"[bold blue]Initializing Pipeline Orchestrator[/bold blue] (Config: {args.config})")
    
    # ---------------------------------------------------------
    # PHASE 1-3: ETL PIPELINE (Extract -> OCR -> Clean)
    # ---------------------------------------------------------
    if config.pipeline.steps.extract.enabled or config.pipeline.steps.ocr.enabled or config.pipeline.steps.clean.enabled:
        pipeline = IngestionPipeline(config)
        if args.file:
            await pipeline.process_file(args.file)
        else:
            await pipeline.process_targets()

    # ---------------------------------------------------------
    # PHASE 4: INDEXING PIPELINE
    # ---------------------------------------------------------
    if config.indexing.enabled:
        console.print(f"\\n[bold blue]Starting Indexing Pipeline[/bold blue]")
        pipeline = IndexingPipeline()
        await pipeline.initialize(args.config)
        await pipeline.process_directory(config.io.directories.output)

    # ---------------------------------------------------------
    # PHASE 5: SUMMARISATION
    # ---------------------------------------------------------
    if config.summarisation.enabled:
        console.print(f"\\n[bold blue]Starting Summarisation Pipeline[/bold blue]")
        # To be implemented
        pass

    console.print("\\n[bold green]Pipeline execution completed.[/bold green]")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
