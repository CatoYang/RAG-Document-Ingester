import argparse
import sys
sys.stdout.reconfigure(encoding='utf-8')
from rich.console import Console

from src.pipeline import IngestionPipeline
from src.indexing.pipeline import IndexingPipeline

console = Console()

import asyncio

async def async_main():
    parser = argparse.ArgumentParser(description="Enterprise Document Ingestion Pipeline for RAG")
    parser.add_argument(
        "--action",
        type=str,
        choices=["extract", "index"],
        default="extract",
        help="Action to perform: 'extract' raw files to markdown, or 'index' markdown to vector DB."
    )
    parser.add_argument(
        "--config", 
        type=str, 
        default="config/config.yaml", 
        help="Path to the YAML configuration file (default: config/config.yaml)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Process a specific file instead of the entire input directory (only applicable for 'extract')."
    )
    
    args = parser.parse_args()
    
    if args.action == "extract":
        console.print(f"[bold blue]Starting Extraction Pipeline[/bold blue] (Config: {args.config})")
        pipeline = IngestionPipeline(config_path=args.config)
        
        if args.file:
            await pipeline.process_file(args.file)
        else:
            await pipeline.process_targets()
            
    elif args.action == "index":
        console.print(f"[bold blue]Starting Indexing Pipeline[/bold blue] (Config: {args.config})")
        pipeline = IndexingPipeline()
        await pipeline.initialize(args.config)
        await pipeline.process_directory(pipeline.config.get("pipeline", {}).get("output_dir", "data/staging_markdown"))
        
    console.print("[bold green]Pipeline execution completed.[/bold green]")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
