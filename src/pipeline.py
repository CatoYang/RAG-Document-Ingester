import os
import yaml
import asyncio
import aiofiles
from pathlib import Path
from rich.console import Console

from src.config.settings import load_config
from src.router.document_router import DocumentRouter
from src.utils.cleaner import DocumentCleaner
from src.core.interfaces import Document

console = Console()

class IngestionPipeline:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        self.router = DocumentRouter(self.config)
        self.mode = self.config.pipeline.mode
        
        # Resolve project root to avoid pathing issues
        project_root = Path(__file__).resolve().parent.parent
        
        # Ensure directories exist
        for i, target in enumerate(self.config.pipeline.targets):
            target_path = Path(target)
            if not target_path.is_absolute():
                target_path = project_root / target_path
                self.config.pipeline.targets[i] = str(target_path)
            if target_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                
        out_dir = Path(self.config.pipeline.output_dir)
        if not out_dir.is_absolute():
            out_dir = project_root / out_dir
            self.config.pipeline.output_dir = str(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
    def _extract(self, file_path: str) -> Document:
        """Runs the file through the router and extractor."""
        extractor = self.router.get_extractor(file_path)
        return extractor.extract(file_path)

    def _read_markdown(self, file_path: str) -> Document:
        """Reads a markdown file, attempting to separate frontmatter from content."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        metadata = {"source": Path(file_path).name, "mode": "clean_only"}
        body = content
        
        # Simple frontmatter parsing if it exists
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    metadata = yaml.safe_load(parts[1]) or metadata
                    body = parts[2].lstrip()
                except Exception:
                    pass
                    
        return Document(source_file=Path(file_path).name, content=body, metadata=metadata)

    async def process_file(self, file_path: str):
        """Processes a single file based on the configured mode."""
        try:
            output_filename = Path(file_path).with_suffix('.md').name
            output_path = Path(self.config.pipeline.output_dir) / output_filename
            
            if output_path.exists():
                console.print(f"[yellow]Skipping {file_path} (already extracted: {output_filename})[/yellow]")
                return

            is_markdown = Path(file_path).suffix.lower() == '.md'
            
            if self.mode == "clean_only":
                if not is_markdown:
                    console.print(f"[yellow]Skipping {file_path} in clean_only mode (not a markdown file).[/yellow]")
                    return
                console.print(f"  [dim]- Reading existing markdown...[/dim]")
                document = await asyncio.to_thread(self._read_markdown, file_path)
            else:
                console.print(f"  [dim]- Extracting document text...[/dim]")
                document = await asyncio.to_thread(self._extract, file_path)
            
            # Apply cleaning if not extract_only
            if self.mode in ["clean_only", "extract_and_clean"]:
                console.print(f"  [dim]- Applying cleaner rules...[/dim]")
                
                # Determine original extension
                original_source = document.metadata.get("source", file_path)
                ext = Path(original_source).suffix.lower()
                
                cleanup_settings = self.config.cleanup_rules # Default global
                if ext in self.config.file_rules and self.config.file_rules[ext].cleanup_rules:
                    cleanup_settings = self.config.file_rules[ext].cleanup_rules
                    
                file_cleaner = DocumentCleaner(cleanup_settings)
                document.content = file_cleaner.clean(document.content)
                document.metadata['cleaner_settings'] = cleanup_settings.model_dump()
                
                # Dynamic LLM Cleaner
                dynamic_cfg = self.config.pipeline.model_dump().get('dynamic_cleaner', {})
                if dynamic_cfg.get('enabled'):
                    from src.utils.dynamic_cleaner import DynamicLLMCleaner
                    dyn_cleaner = DynamicLLMCleaner(dynamic_cfg)
                    document.content, review_reqs = await dyn_cleaner.clean(document.content, document.source_file)
                    
                    if review_reqs:
                        import json
                        import aiofiles
                        review_path = Path(self.config.pipeline.output_dir) / "review_required.json"
                        existing = []
                        if review_path.exists():
                            async with aiofiles.open(review_path, "r") as f:
                                content = await f.read()
                                if content:
                                    existing = json.loads(content)
                        existing.extend(review_reqs)
                        async with aiofiles.open(review_path, "w") as f:
                            await f.write(json.dumps(existing, indent=4))
                        console.print(f"[yellow]Flagged {len(review_reqs)} ambiguous patterns for manual review in review_required.json[/yellow]")
            
            output_filename = Path(file_path).with_suffix('.md').name
            output_path = Path(self.config.pipeline.output_dir) / output_filename
            
            # Serialize metadata to YAML frontmatter
            frontmatter = f"---\n{yaml.dump(document.metadata, sort_keys=False)}---\n\n"
            final_content = frontmatter + document.content
            
            import aiofiles
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(final_content)
                
            console.print(f"[bold green]Successfully saved to {output_path}[/bold green]")
            
            if "Eberron Campaign Setting.pdf" in file_path:
                console.print("[bold red]Stopping script after Eberron Campaign Setting.pdf as requested.[/bold red]")
                import sys
                sys.exit(0)
                
        except Exception as e:
            console.print(f"[bold red]Failed to process {file_path}: {e}[/bold red]")
            
    async def process_targets(self):
        """Processes all files and directories specified in the config targets."""
        supported_extensions = list(self.config.file_rules.keys())
        files_to_process = []
        
        for target_str in self.config.pipeline.targets:
            target = Path(target_str)
            
            if target.is_file() and target.suffix.lower() in supported_extensions:
                files_to_process.append(target)
            elif target.is_dir():
                for f in target.rglob('*'):
                    if f.is_file() and f.suffix.lower() in supported_extensions:
                        files_to_process.append(f)
            else:
                console.print(f"[yellow]Target '{target_str}' not found or unsupported.[/yellow]")
        
        unique_files = list(set(files_to_process))
        
        from src.utils.deduplicator import DocumentDeduplicator
        deduplicator = DocumentDeduplicator(self.config.pipeline.deduplication)
        unique_files = deduplicator.filter_duplicates(unique_files)
        
        if not unique_files:
            console.print("[yellow]No supported files found in targets.[/yellow]")
            return
            
        console.print(f"[cyan]Found {len(unique_files)} unique files to process in '{self.mode}' mode.[/cyan]")
        
        for file in unique_files:
            console.print(f"\n[bold]Processing: {file.name}[/bold]")
            await self.process_file(str(file))
