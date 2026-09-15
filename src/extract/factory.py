import json
from pathlib import Path
from typing import Dict, Tuple
from rich.console import Console

from src.core.interfaces import BaseRouter, BaseExtractor
from src.config.settings import Config
from src.extract.registry import get_extractor_class

console = Console()


class DocumentRouter(BaseRouter):
    """Triages documents and assigns the appropriate extractor."""

    def __init__(self, config: Config):
        self.config = config
        # Extractors (notably PdfExtractor/Marker) can be expensive to
        # construct - they load a full set of GPU models. Without caching,
        # every file in a multi-file run reloads them from scratch. Keyed by
        # (extractor class, sorted params) so different file_rules using the
        # same extractor with different params get distinct instances.
        self._extractor_cache: Dict[Tuple[type, str], BaseExtractor] = {}

    def _get_or_create_extractor(self, extractor_cls: type, params: dict) -> BaseExtractor:
        try:
            # json.dumps (not a tuple of .items()) so nested dict/list param
            # values (e.g. AutoPdfExtractor's ocr_params) are still hashable
            # as part of the cache key.
            cache_key = (extractor_cls, json.dumps(params, sort_keys=True, default=str))
        except TypeError:
            # Still not serializable - fall back to an uncached instance
            # rather than failing the whole run.
            return extractor_cls(**params)

        if cache_key not in self._extractor_cache:
            self._extractor_cache[cache_key] = extractor_cls(**params)
        return self._extractor_cache[cache_key]

    def get_extractor(self, file_path: str) -> BaseExtractor:
        """Determines the appropriate extractor based on file extension and config."""
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext not in self.config.file_rules:
            raise ValueError(
                f"Unsupported file type or missing in config: {ext}")

        rule = self.config.file_rules[ext]

        try:
            extractor_cls = get_extractor_class(rule.extractor)
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
            # Fallback
            if rule.fallback:
                console.print(
                    f"[yellow]Attempting fallback to {rule.fallback}...[/yellow]")
                extractor_cls = get_extractor_class(rule.fallback)
            else:
                raise

        console.print(
            f"[green]Routing {path.name} to {extractor_cls.__name__}...[/green]")
        return self._get_or_create_extractor(extractor_cls, rule.params)
