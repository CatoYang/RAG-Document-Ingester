import os
import yaml
import aiofiles
from pathlib import Path
from rich.console import Console
from datetime import datetime

from src.core.interfaces import Document
from src.config.settings import Config
from src.extract.factory import DocumentRouter
from src.clean.cleaner import DocumentCleaner

console = Console()

class IngestionPipeline:
    """Orchestrates the extraction, OCR transcription, and cleaning phases using an idempotent state machine."""

    def __init__(self, config: Config):
        self.config = config
        self.router = DocumentRouter(config)
        self.cleaner = DocumentCleaner(config.cleanup_rules)

    async def _load_staged_document(self, staging_path: Path, source_file: str) -> Document:
        """Loads a document and parses its frontmatter state."""
        if not staging_path.exists():
            return None
            
        async with aiofiles.open(staging_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            
        if content.startswith("---"):
            try:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    metadata = yaml.safe_load(parts[1])
                    body = parts[2].lstrip()
                    return Document(source_file=source_file, content=body, metadata=metadata)
            except yaml.YAMLError:
                pass
                
        return Document(source_file=source_file, content=content, metadata={})

    async def process_file(self, file_path: str):
        path = Path(file_path)
        base_name = path.stem
        
        staging_dir = Path(self.config.io.directories.staging)
        output_dir = Path(self.config.io.directories.output)
        staging_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # State tracking file
        staging_path = staging_dir / f"{base_name}.md"
        
        # Check if already fully finished
        if (output_dir / f"{base_name}.md").exists():
            console.print(f"[dim]Skipping {base_name} (Already in output directory)[/dim]")
            return

        steps = self.config.pipeline.steps
        current_document = await self._load_staged_document(staging_path, path.name)
        
        # ---------------------------------------------------------
        # PHASE 1: EXTRACTION
        # ---------------------------------------------------------
        phases = current_document.metadata.get("pipeline_phases", []) if current_document else []
        
        if steps.extract.enabled and "extract" not in phases:
            console.print(f"[cyan]Phase 1: Extracting {path.name}...[/cyan]")
            extractor = self.router.get_extractor(str(path))
            current_document = extractor.extract(str(path), output_dir=str(staging_dir))
            
            if not current_document:
                console.print(f"[red]Extraction failed for {path.name}[/red]")
                return
                
            current_document.metadata["pipeline_phases"] = ["extract"]
            await self._save_document(current_document, staging_path)
            phases = current_document.metadata["pipeline_phases"]

        if not current_document:
            return

        # ---------------------------------------------------------
        # PHASE 2: IMAGE OCR / TRANSCRIPTION
        # ---------------------------------------------------------
        if steps.ocr.enabled and "ocr" not in phases:
            from src.vision.orchestrator import process_ocr
            
            console.print(f"[cyan]Phase 2: Vision OCR (Mode: {steps.ocr.mode})...[/cyan]")
            
            # process_ocr might suspend processing (async batch) or complete immediately
            suspended = await process_ocr(current_document, self.config)
            
            if suspended:
                console.print(f"[yellow]>> {path.name} suspended. Awaiting Async Batch API completion.[/yellow]")
                return
                
            # If not suspended, it's done!
            current_document.metadata["pipeline_phases"].append("ocr")
            await self._save_document(current_document, staging_path)
            phases = current_document.metadata["pipeline_phases"]

        # ---------------------------------------------------------
        # PHASE 3: TEXT CLEANING
        # ---------------------------------------------------------
        if steps.clean.enabled and "clean" not in phases:
            console.print(f"[cyan]Phase 3: Cleaning text for {path.name}...[/cyan]")
            
            cleaned_content = self.cleaner.clean(current_document.content)
            current_document.content = cleaned_content
            current_document.metadata["pipeline_phases"].append("clean")
            
            await self._save_document(current_document, staging_path)

        # ---------------------------------------------------------
        # FINAL OUTPUT
        # ---------------------------------------------------------
        final_path = output_dir / f"{base_name}.md"
        await self._save_document(current_document, final_path)
        console.print(f"[bold green]Successfully completed pipeline for {path.name} -> {final_path}[/bold green]")
        
        # Cleanup staging file if we want
        # if staging_path.exists():
        #    os.remove(staging_path)

    async def _save_document(self, document, output_path: Path):
        try:
            frontmatter = f"---\\n{yaml.dump(document.metadata, sort_keys=False)}---\\n\\n"
            final_content = frontmatter + document.content

            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(final_content)
        except Exception as e:
            console.print(f"[bold red]Failed to save {output_path}: {e}[/bold red]")

    async def process_targets(self):
        """Processes all files in inputs."""
        supported_extensions = list(self.config.file_rules.keys())
        files_to_process = []

        for target_str in self.config.io.input_targets:
            target = Path(target_str)
            if target.is_file() and target.suffix.lower() in supported_extensions:
                files_to_process.append(target)
            elif target.is_dir():
                for f in target.rglob('*'):
                    if f.is_file() and f.suffix.lower() in supported_extensions:
                        files_to_process.append(f)

        unique_files = list(set(files_to_process))
        
        # Binary File Deduplication (Phase 1 pre-flight check)
        from src.extract.deduplicator import DocumentDeduplicator
        deduplicator = DocumentDeduplicator(self.config.pipeline.deduplication)
        unique_files = deduplicator.filter_duplicates(unique_files)
        
        # Exclude completed files
        output_dir = Path(self.config.io.directories.output)
        filtered = [f for f in unique_files if not (output_dir / f"{f.stem}.md").exists()]

        console.print(f"[cyan]Found {len(filtered)} files to process in the ETL pipeline.[/cyan]")

        for file in filtered:
            console.print(f"\\n[bold]Processing: {file.name}[/bold]")
            await self.process_file(str(file))
