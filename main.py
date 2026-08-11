import argparse
from rich.console import Console

from src.pipeline import IngestionPipeline
from src.indexing.pipeline import IndexingPipeline

console = Console()

def main():
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
        default="config.yaml", 
        help="Path to the YAML configuration file (default: config.yaml)"
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
            pipeline.process_file(args.file)
        else:
            pipeline.process_targets()
            
    elif args.action == "index":
        console.print(f"[bold blue]Starting Indexing Pipeline[/bold blue] (Config: {args.config})")
        pipeline = IndexingPipeline(config_path=args.config)
        # We index everything in staging_markdown
        pipeline.process_directory("data/staging_markdown")
        
    console.print("[bold green]Pipeline execution completed.[/bold green]")

if __name__ == "__main__":
    main()
