import pytest
import tempfile
import os
import yaml
from pathlib import Path
from src.config.settings import Config

@pytest.fixture
def temp_workspace():
    """Creates a temporary workspace structure to prevent leakage to data/."""
    with tempfile.TemporaryDirectory() as td:
        base_dir = Path(td)
        raw_dir = base_dir / "raw"
        staging_dir = base_dir / "staging"
        output_dir = base_dir / "output"
        
        raw_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        yield {
            "base": base_dir,
            "raw": raw_dir,
            "staging": staging_dir,
            "output": output_dir
        }

@pytest.fixture
def mock_config(temp_workspace):
    """Generates a Config object pointing to the temp_workspace."""
    config_data = {
        "io": {
            "input_targets": [str(temp_workspace["raw"])],
            "directories": {
                "assets": str(temp_workspace["staging"] / "assets"),
                "staging": str(temp_workspace["staging"]),
                "batch_jobs": str(temp_workspace["staging"] / "batch_jobs"),
                "output": str(temp_workspace["output"])
            }
        },
        "pipeline": {
            "steps": {
                "extract": {"enabled": True, "save_intermediate": True},
                "ocr": {"enabled": False, "mode": "passthrough", "provider": "gemini", "model": "test"},
                "clean": {"enabled": True, "save_intermediate": False}
            },
            "deduplication": {"enabled": False, "method": "size"}
        },
        "cleanup_rules": {
            "collapse_newlines": True,
            "remove_zero_width_spaces": True,
            "trim_trailing_whitespace": True,
            "regex_removals": ["(?m)^Page \\d+$"]
        },
        "file_rules": {
            ".txt": {
                "extractor": "MarkItDownExtractor",
                "fallback": "MarkItDownExtractor"
            }
        },
        "indexing": {"enabled": False, "chunker": {"type": "MarkdownChunker"}, "embedder": {"type": "OllamaEmbedder"}, "vectorstore": {"type": "QdrantStore"}},
        "summarisation": {"enabled": False, "provider": "ollama"}
    }
    return Config(**config_data)
