import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class IODirectories(BaseModel):
    assets: str = Field(default="data/staging/assets")
    staging: str = Field(default="data/staging")
    batch_jobs: str = Field(default="data/staging/batch_jobs")
    output: str = Field(default="data/output/final_markdown")

class IOSettings(BaseModel):
    input_targets: List[str] = Field(default_factory=lambda: ["data/raw"])
    directories: IODirectories = Field(default_factory=IODirectories)

class PipelineStep(BaseModel):
    enabled: bool = Field(default=True)
    save_intermediate: bool = Field(default=False)
    intermediate_suffix: str = Field(default="_intermediate")

class OcrStep(PipelineStep):
    mode: str = Field(default="passthrough")
    provider: str = Field(default="gemini")
    model: str = Field(default="gemini-1.5-flash")

class PipelineSteps(BaseModel):
    extract: PipelineStep = Field(default_factory=lambda: PipelineStep(intermediate_suffix="_raw"))
    ocr: OcrStep = Field(default_factory=lambda: OcrStep(intermediate_suffix="_ocr"))
    clean: PipelineStep = Field(default_factory=lambda: PipelineStep(intermediate_suffix="_clean"))

class DeduplicationSettings(BaseModel):
    enabled: bool = Field(default=True)
    method: str = Field(default="exact")

class PipelineSettings(BaseModel):
    steps: PipelineSteps = Field(default_factory=PipelineSteps)
    deduplication: DeduplicationSettings = Field(default_factory=DeduplicationSettings)
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
    enabled: bool = Field(default=False)
    chunker: ChunkerSettings = Field(default_factory=ChunkerSettings)
    embedder: EmbedderSettings = Field(default_factory=EmbedderSettings)
    vectorstore: VectorStoreSettings = Field(default_factory=VectorStoreSettings)

class Config(BaseModel):
    io: IOSettings = Field(default_factory=IOSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    cleanup_rules: CleanupSettings = Field(default_factory=CleanupSettings)
    file_rules: Dict[str, FileRule] = Field(default_factory=dict)
    summarisation: SummarisationSettings = Field(default_factory=SummarisationSettings)
    indexing: IndexingSettings = Field(default_factory=IndexingSettings)

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
