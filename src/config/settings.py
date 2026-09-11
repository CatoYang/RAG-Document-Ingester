import yaml
from pathlib import Path
from pydantic import BaseModel, Field

from typing import List, Optional, Dict, Any


class DeduplicationSettings(BaseModel):
    enabled: bool = Field(default=True)
    method: str = Field(default="exact")


class PipelineStep(BaseModel):
    enabled: bool = Field(default=True)
    save_intermediate: bool = Field(default=False)
    intermediate_suffix: str = Field(default="_intermediate")

class PipelineSteps(BaseModel):
    extract: PipelineStep = Field(default_factory=lambda: PipelineStep(intermediate_suffix="_raw"))
    clean: PipelineStep = Field(default_factory=lambda: PipelineStep(intermediate_suffix="_clean"))

class PipelineSettings(BaseModel):
    steps: PipelineSteps = Field(default_factory=PipelineSteps)
    targets: List[str] = Field(default_factory=lambda: ["data/raw"])
    output_dir: str = Field(default="data/staging/staging_markdown")
    deduplication: DeduplicationSettings = Field(
        default_factory=DeduplicationSettings)
    dynamic_cleaner: Dict[str, Any] = Field(default_factory=dict)


class CleanupSettings(BaseModel):
    collapse_newlines: bool = Field(default=True)
    remove_zero_width_spaces: bool = Field(default=True)
    trim_trailing_whitespace: bool = Field(default=True)
    deduplicate_paragraphs: bool = Field(default=False)
    regex_removals: List[str] = Field(default_factory=list)


class FileRule(BaseModel):
    extractor: str
    fallback: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    cleanup_rules: Optional[CleanupSettings] = None


class SummarisationSettings(BaseModel):
    enabled: bool = Field(default=False)
    provider: str = Field(default="ollama")
    params: Dict[str, Any] = Field(default_factory=dict)


class ChunkerSettings(BaseModel):
    type: str = Field(default="MarkdownChunker")
    params: Dict[str, Any] = Field(default_factory=dict)


class EmbedderSettings(BaseModel):
    type: str = Field(default="OllamaEmbedder")
    params: Dict[str, Any] = Field(default_factory=dict)


class VectorStoreSettings(BaseModel):
    type: str = Field(default="ChromaDBStore")
    params: Dict[str, Any] = Field(default_factory=dict)


class IndexingSettings(BaseModel):
    chunker: ChunkerSettings = Field(default_factory=ChunkerSettings)
    embedder: EmbedderSettings = Field(default_factory=EmbedderSettings)
    vectorstore: VectorStoreSettings = Field(
        default_factory=VectorStoreSettings)


class Config(BaseModel):
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    cleanup_rules: CleanupSettings = Field(default_factory=CleanupSettings)
    file_rules: Dict[str, FileRule] = Field(default_factory=dict)
    summarisation: SummarisationSettings = Field(
        default_factory=SummarisationSettings)
    indexing: IndexingSettings = Field(default_factory=IndexingSettings)


def load_config(config_path: str = "config/config.yaml") -> Config:
    path = Path(config_path)

    # To prevent pathing issues, if the path is relative and doesn't exist in CWD,
    # try resolving it relative to the project root.
    if not path.is_absolute() and not path.exists():
        project_root = Path(__file__).resolve().parent.parent.parent
        path = project_root / path

    if not path.exists():
        return Config()  # return defaults

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        if not data:
            data = {}

    return Config(**data)
