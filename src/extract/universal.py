from pathlib import Path
from datetime import datetime
from markitdown import MarkItDown
from src.core.interfaces import BaseExtractor, Document
import importlib.metadata


class MarkItDownExtractor(BaseExtractor):
    """Tier 2 Extractor: Universal parser for Office, Web, and Data formats."""

    def __init__(self):
        self.md = MarkItDown()

    def extract(self, file_path: str, **kwargs) -> Document:
        file_path_obj = Path(file_path)

        # Convert using MarkItDown
        result = self.md.convert(file_path)

        try:
            version = importlib.metadata.version("markitdown")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"

        metadata = {
            "source": file_path_obj.name,
            "date_ingested": datetime.now().replace(
                microsecond=0).isoformat(' '),
            "extractor": {
                "program": "markitdown",
                "version": version,
                "mode": "universal_text"}}

        return Document(
            source_file=file_path_obj.name,
            content=result.text_content,
            metadata=metadata
        )
