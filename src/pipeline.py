import os
import yaml
import asyncio
from pathlib import Path
import aiofiles
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
        return extractor.extract(
            file_path, output_dir=self.config.pipeline.output_dir)

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

        return Document(
            source_file=Path(file_path).name,
            content=body,
            metadata=metadata)

    async def process_file(self, file_path: str):
        """Processes a single file based on the configured steps."""
        try:
            output_filename = Path(file_path).with_suffix('.md').name
            output_path = Path(self.config.pipeline.output_dir) / output_filename

            if output_path.exists():
                console.print(f"[yellow]Skipping {file_path} (already extracted: {output_filename})[/yellow]")
                return

            is_markdown = Path(file_path).suffix.lower() == '.md'
            document = None
            
            steps = self.config.pipeline.steps

            # 1. Extraction Step
            if steps.extract.enabled:
                console.print(f"  [dim]- Extracting document text...[/dim]")
                document = await asyncio.to_thread(self._extract, file_path)
                
                if steps.extract.save_intermediate:
                    raw_filename = Path(file_path).stem + steps.extract.intermediate_suffix + '.md'
                    raw_path = Path(self.config.pipeline.output_dir) / raw_filename
                    frontmatter = f"---\n{yaml.dump(document.metadata, sort_keys=False)}---\n\n"
                    import aiofiles
                    async with aiofiles.open(raw_path, "w", encoding="utf-8") as f:
                        await f.write(frontmatter + document.content)
                    console.print(f"  [dim]- Saved intermediate extraction to {raw_filename}[/dim]")
            else:
                if not is_markdown:
                    console.print(f"[yellow]Skipping {file_path} (extraction disabled and not a markdown file).[/yellow]")
                    return
                console.print(f"  [dim]- Reading existing markdown...[/dim]")
                document = await asyncio.to_thread(self._read_markdown, file_path)

            # 2. Cleaning Step
            if steps.clean.enabled:
                console.print(f"  [dim]- Applying cleaner rules...[/dim]")

                original_source = document.metadata.get("source", file_path)
                ext = Path(original_source).suffix.lower()

                cleanup_settings = self.config.cleanup_rules
                if ext in self.config.file_rules and self.config.file_rules[ext].cleanup_rules:
                    cleanup_settings = self.config.file_rules[ext].cleanup_rules

                file_cleaner = DocumentCleaner(cleanup_settings)
                document.content = file_cleaner.clean(document.content)
                document.metadata['cleaner_settings'] = cleanup_settings.model_dump()

                dynamic_cfg = self.config.pipeline.model_dump().get('dynamic_cleaner', {})
                if dynamic_cfg.get('enabled'):
                    from src.utils.dynamic_cleaner import DynamicLLMCleaner
                    dyn_cleaner = DynamicLLMCleaner(dynamic_cfg)
                    document.content, review_reqs = await dyn_cleaner.clean(document.content, document.source_file)

                    if review_reqs:
                        import json
                        review_path = Path(self.config.pipeline.output_dir) / "review_required.json"
                        existing = []
                        if review_path.exists():
                            import aiofiles
                            async with aiofiles.open(review_path, "r") as f:
                                content = await f.read()
                                if content:
                                    existing = json.loads(content)
                        existing.extend(review_reqs)
                        import aiofiles
                        async with aiofiles.open(review_path, "w") as f:
                            await f.write(json.dumps(existing, indent=4))
                        console.print(f"[yellow]Flagged {len(review_reqs)} ambiguous patterns for manual review in review_required.json[/yellow]")

                if steps.clean.save_intermediate:
                    clean_filename = Path(file_path).stem + steps.clean.intermediate_suffix + '.md'
                    clean_path = Path(self.config.pipeline.output_dir) / clean_filename
                    frontmatter = f"---\n{yaml.dump(document.metadata, sort_keys=False)}---\n\n"
                    import aiofiles
                    async with aiofiles.open(clean_path, "w", encoding="utf-8") as f:
                        await f.write(frontmatter + document.content)
                    console.print(f"  [dim]- Saved intermediate cleaning to {clean_filename}[/dim]")

            # Final Save
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

    def _verify_environment(self):
        """Pre-flight check to verify model availability and VRAM integrity before the pipeline starts."""
        console.print("[cyan]Running pre-flight environment checks...[/cyan]")

        # Gather all models defined in the config
        ollama_models = set()

        # Check extractor models and DPI
        high_dpi_rules = []
        for ext, rule in self.config.file_rules.items():
            if "VLM" in rule.extractor or "LLM" in rule.extractor or "Hybrid" in rule.extractor:
                model = rule.params.get("vlm_model") or rule.params.get(
                    "model", "minicpm-v")
                if "gemini" not in model.lower():
                    ollama_models.add(model)

            if rule.extractor in [
                "PdfVLMExtractor",
                "ImageVLMExtractor",
                    "HybridPdfExtractor"]:
                dpi = rule.params.get("dpi", 300)
                if dpi > 150:
                    high_dpi_rules.append(f"{rule.extractor} ({ext})")

        if high_dpi_rules:
            console.print(
                f"[yellow]WARNING: High DPI (>150) detected on {', '.join(high_dpi_rules)}. High DPI can cause context window VRAM overflow![/yellow]")

        # Check summarisation models
        if self.config.summarisation.enabled and self.config.summarisation.provider == "ollama":
            model = self.config.summarisation.params.get("model", "llama3")
            ollama_models.add(model)

        # Check embedder models
        if hasattr(
                self.config,
                'indexing') and self.config.indexing.embedder.type == "OllamaEmbedder":
            model = self.config.indexing.embedder.params.get(
                "model", "nomic-embed-text")
            ollama_models.add(model)

        if not ollama_models:
            return

        import urllib.request
        import urllib.error
        import json

        host = "http://127.0.0.1:11434"
        if "WSL_DISTRO_NAME" in os.environ:
            import subprocess
            try:
                result = subprocess.run(
                    ['ip', 'route'], capture_output=True, text=True, check=True)
                for line in result.stdout.split('\n'):
                    if line.startswith('default via'):
                        wsl_ip = line.split(' ')[2]
                        host = f"http://{wsl_ip}:11434"
                        break
            except Exception:
                pass

        # Ping Ollama and verify integrity
        try:
            req = urllib.request.Request(f"{host}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as response:
                tags_data = json.loads(response.read().decode())
                available_models = [m['name']
                                    for m in tags_data.get('models', [])]

            for model in ollama_models:
                # Basic check if model exists
                model_base = model.split(':')[0]
                found = any(m.startswith(model_base) for m in available_models)
                if not found:
                    console.print(
                        f"[bold red]WARNING: Configured model '{model}' was not found in Ollama! Run 'ollama pull {model}'.[/bold red]")
                    continue

                # Preload the model to check VRAM
                console.print(
                    f"  [dim]- Verifying VRAM integrity for {model}...[/dim]")

                # Send dummy generate request to load it into memory
                load_req = urllib.request.Request(
                    f"{host}/api/generate",
                    data=json.dumps({"model": model, "prompt": "", "keep_alive": "5m"}).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )
                try:
                    with urllib.request.urlopen(load_req, timeout=30) as _:
                        pass
                except urllib.error.URLError:
                    pass

                # Check ps endpoint to see if it offloaded to CPU RAM
                ps_req = urllib.request.Request(f"{host}/api/ps")
                with urllib.request.urlopen(ps_req, timeout=5) as ps_response:
                    ps_data = json.loads(ps_response.read().decode())
                    for m in ps_data.get('models', []):
                        if m.get('name', '').startswith(model_base):
                            size = m.get('size', 0)
                            size_vram = m.get('size_vram', 0)
                            if size > 0 and size_vram < size * 0.95:
                                console.print(
                                    f"[bold red]CRITICAL WARNING: Model '{model}' offloaded to system RAM (VRAM {size_vram // (1024**2)}MB / Total {size // (1024**2)}MB).[/bold red]")
                                console.print(
                                    "[bold red]The pipeline will choke and run extremely slowly. Please switch to a smaller model or lower the DPI setting for Vision models.[/bold red]")
                                raise MemoryError(
                                    f"Pre-flight failed: VRAM overflow for {model}")
                            else:
                                console.print(
                                    f"  [green]- {model} successfully loaded into VRAM.[/green]")
        except urllib.error.URLError:
            console.print(
                "[bold red]WARNING: Could not connect to Ollama. Ensure Ollama is running.[/bold red]")
        except MemoryError:
            raise
        except Exception as e:
            console.print(
                f"[yellow]Could not complete VRAM integrity check: {e}[/yellow]")

    async def process_targets(self):
        """Processes all files and directories specified in the config targets."""
        self._verify_environment()

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
                console.print(
                    f"[yellow]Target '{target_str}' not found or unsupported.[/yellow]")

        unique_files = list(set(files_to_process))

        from src.utils.deduplicator import DocumentDeduplicator
        deduplicator = DocumentDeduplicator(self.config.pipeline.deduplication)
        unique_files = deduplicator.filter_duplicates(unique_files)

        if not unique_files:
            console.print(
                "[yellow]No supported files found in targets.[/yellow]")
            return

        console.print(
            f"[cyan]Found {len(unique_files)} unique files to process .[/cyan]")

        for file in unique_files:
            console.print(f"\n[bold]Processing: {file.name}[/bold]")
            await self.process_file(str(file))
