import yaml
from pathlib import Path
from pydantic import BaseModel, Field

from typing import List, Optional, Dict, Any

class PipelineSettings(BaseModel):
    mode: str = Field(default="extract_and_clean")
    targets: List[str] = Field(default_factory=lambda: ["data/raw"])
    output_dir: str = Field(default="data/staging_markdown")

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

class Config(BaseModel):
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    cleanup_rules: CleanupSettings = Field(default_factory=CleanupSettings)
    file_rules: Dict[str, FileRule] = Field(default_factory=dict)

def load_config(config_path: str = "config.yaml") -> Config:
    path = Path(config_path)
    if not path.exists():
        return Config() # return defaults
        
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        if not data:
            data = {}
            
    return Config(**data)
