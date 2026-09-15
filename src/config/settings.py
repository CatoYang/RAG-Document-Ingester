import yaml
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any


class StrictModel(BaseModel):
    """Base for every config model: rejects unknown/misspelled keys instead
    of silently dropping them (e.g. legacy `pipeline.mode`/`strip_regex`),
    so a typo'd config fails loudly at `load_config()` instead of quietly
    doing nothing."""
    model_config = ConfigDict(extra="forbid")


class IODirectories(StrictModel):
    assets: str = Field(default="data/staging/assets")
    staging: str = Field(default="data/staging")
    batch_jobs: str = Field(default="data/staging/batch_jobs")
    output: str = Field(default="data/output/final_markdown")

class IOSettings(StrictModel):
    input_targets: List[str] = Field(default_factory=lambda: ["data/raw"])
    directories: IODirectories = Field(default_factory=IODirectories)

class PipelineStep(StrictModel):
    enabled: bool = Field(default=True)
    save_intermediate: bool = Field(default=False)
    intermediate_suffix: str = Field(default="_intermediate")

class OcrStep(PipelineStep):
    mode: str = Field(default="passthrough")
    provider: str = Field(default="gemini")
    model: str = Field(default="gemini-1.5-flash")

class PipelineSteps(StrictModel):
    extract: PipelineStep = Field(default_factory=lambda: PipelineStep(intermediate_suffix="_raw"))
    ocr: OcrStep = Field(default_factory=lambda: OcrStep(intermediate_suffix="_ocr"))
    clean: PipelineStep = Field(default_factory=lambda: PipelineStep(intermediate_suffix="_clean"))

class DeduplicationSettings(StrictModel):
    enabled: bool = Field(default=True)
    method: str = Field(default="exact")

class PipelineSettings(StrictModel):
    steps: PipelineSteps = Field(default_factory=PipelineSteps)
    deduplication: DeduplicationSettings = Field(default_factory=DeduplicationSettings)
    dynamic_cleaner: Dict[str, Any] = Field(default_factory=dict)

class CleanupSettings(StrictModel):
    collapse_newlines: bool = Field(default=True)
    remove_zero_width_spaces: bool = Field(default=True)
    trim_trailing_whitespace: bool = Field(default=True)
    deduplicate_paragraphs: bool = Field(default=False)
    regex_removals: List[str] = Field(default_factory=list)

class FileRule(StrictModel):
    extractor: str
    fallback: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    cleanup_rules: Optional[CleanupSettings] = None

class SummarisationSettings(StrictModel):
    enabled: bool = Field(default=False)
    provider: str = Field(default="ollama")
    params: Dict[str, Any] = Field(default_factory=dict)

class ChunkerSettings(StrictModel):
    type: str = Field(default="MarkdownChunker")
    params: Dict[str, Any] = Field(default_factory=dict)

class EmbedderSettings(StrictModel):
    type: str = Field(default="OllamaEmbedder")
    params: Dict[str, Any] = Field(default_factory=dict)

class VectorStoreSettings(StrictModel):
    type: str = Field(default="ChromaDBStore")
    params: Dict[str, Any] = Field(default_factory=dict)

class IndexingSettings(StrictModel):
    enabled: bool = Field(default=False)
    chunker: ChunkerSettings = Field(default_factory=ChunkerSettings)
    embedder: EmbedderSettings = Field(default_factory=EmbedderSettings)
    vectorstore: VectorStoreSettings = Field(default_factory=VectorStoreSettings)

class ChatSettings(StrictModel):
    model: str = Field(default="llama3")
    top_k: int = Field(default=5, ge=1)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)

class Config(StrictModel):
    io: IOSettings = Field(default_factory=IOSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    cleanup_rules: CleanupSettings = Field(default_factory=CleanupSettings)
    file_rules: Dict[str, FileRule] = Field(default_factory=dict)
    summarisation: SummarisationSettings = Field(default_factory=SummarisationSettings)
    indexing: IndexingSettings = Field(default_factory=IndexingSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)

def load_config(config_path: str = "config/config.yaml") -> Config:
    path = Path(config_path)
    if not path.is_absolute() and not path.exists():
        project_root = Path(__file__).resolve().parent.parent.parent
        path = project_root / path

    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found at {path}. "
            "Please copy 'config/config_template.yaml' to 'config/config.yaml' or specify a valid --config path."
        )

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        if not data:
            data = {}

    # Migrate legacy pipeline targets/output_dir mapping so tests don't break
    if "pipeline" in data:
        legacy_targets = data["pipeline"].pop("targets", None)
        legacy_output = data["pipeline"].pop("output_dir", None)
        if legacy_targets or legacy_output:
            if "io" not in data:
                data["io"] = {}
            if legacy_targets and "input_targets" not in data["io"]:
                data["io"]["input_targets"] = legacy_targets
            if legacy_output:
                if "directories" not in data["io"]:
                    data["io"]["directories"] = {}
                if "staging" not in data["io"]["directories"]:
                    data["io"]["directories"]["staging"] = legacy_output

    return Config(**data)
