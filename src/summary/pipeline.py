import yaml
import aiofiles
from rich.console import Console
from typing import Dict, List

from src.core.interfaces import Document, Chunk
from src.summary.providers import OllamaSummariser, GeminiSummariser

console = Console()


class SummarisationPipeline:
    def __init__(self):
        self.config = {}
        self.enabled = False
        self.summariser = None

    async def initialize(self, config_path: str = "config/config.yaml"):
        import pathlib
        path = pathlib.Path(config_path)
        if not path.is_absolute() and not path.exists():
            project_root = pathlib.Path(
                __file__).resolve().parent.parent.parent
            path = project_root / path

        async with aiofiles.open(path, 'r') as f:
            content = await f.read()
            self.config = yaml.safe_load(content)

        summary_cfg = self.config.get('summarisation', {})
        self.enabled = summary_cfg.get('enabled', False)

        provider_type = summary_cfg.get('provider', 'ollama')
        params = summary_cfg.get('params', {})

        if provider_type == 'gemini':
            self.summariser = GeminiSummariser(**params)
        else:
            self.summariser = OllamaSummariser(**params)

    async def generate_document_summary(self, doc: Document) -> str:
        if not self.enabled:
            return ""

        console.print(
            f"[dim]Generating document summary for {doc.source_file}...[/dim]")

        max_chars = 15000
        text_to_summarise = doc.content[:max_chars]

        try:
            summary = await self.summariser.summarise(text_to_summarise)
            return summary
        except Exception as e:
            console.print(f"[red]Error generating document summary: {e}[/red]")
            return ""

    async def generate_section_summaries(
            self, chunks: List[Chunk], doc_summary: str) -> Dict[str, str]:
        if not self.enabled:
            return {}

        sections = {}
        for chunk in chunks:
            if chunk.source_metadata.section:
                sections.setdefault(
                    chunk.source_metadata.section,
                    []).append(
                    chunk.text)

        section_summaries = {}
        for section, texts in sections.items():
            combined_text = "\n".join(texts)[:8000]
            try:
                safe_section = section.encode(
                    'ascii', 'replace').decode('ascii')
                console.print(
                    f"[dim]Generating section summary for: {safe_section}[/dim]")
                summary = await self.summariser.summarise(
                    combined_text,
                    context=f"Document Summary: {doc_summary}"
                )
                section_summaries[section] = summary
            except Exception as e:
                console.print(
                    f"[red]Error generating section summary: {e}[/red]")

        return section_summaries
