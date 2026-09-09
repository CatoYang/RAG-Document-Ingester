import os
import sys
from pathlib import Path

# Add project root to sys.path so we can run this from anywhere
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import yaml
from src.config.settings import Config, FileRule, CleanupSettings

def generate_master_config(output_path: str = "config/master_template.yaml"):
    # Create a base config with defaults
    config = Config()
    
    # Populate all possible dictionary variations so they appear in the template
    # Dynamic Cleaner
    config.pipeline.dynamic_cleaner = {
        "enabled": True,
        "provider": "ollama",
        "params": {
            "model": "llama3"
        }
    }
    
    # File Rules (include all major formats)
    config.file_rules = {
        ".pdf": FileRule(
            extractor="PdfVLMExtractor",
            fallback="PdfTextExtractor",
            params={"model": "minicpm-v", "dpi": 300, "temperature": 0.0},
            cleanup_rules=CleanupSettings(
                collapse_newlines=True,
                remove_zero_width_spaces=True,
                trim_trailing_whitespace=True,
                deduplicate_paragraphs=True,
                regex_removals=[
                    '(?m)^```markdown\s*$',
                    '(?m)^```\s*$'
                ]
            )
        ),
        ".docx": FileRule(
            extractor="DocxExtractor",
            fallback="UniversalExtractor",
            params={"strip_comments": True},
            cleanup_rules=CleanupSettings()
        ),
        ".xlsx": FileRule(
            extractor="SpreadsheetExtractor",
            fallback="UniversalExtractor",
            params={"skip_empty_sheets": True},
            cleanup_rules=CleanupSettings()
        ),
        ".html": FileRule(
            extractor="HtmlExtractor",
            fallback="UniversalExtractor",
            params={"strict_content": True},
            cleanup_rules=CleanupSettings()
        ),
        ".txt": FileRule(
            extractor="MarkItDownExtractor"
        ),
        ".png": FileRule(
            extractor="ImageVLMExtractor",
            params={"model": "qwen2.5-vl", "dpi": 200, "temperature": 0.0},
            cleanup_rules=CleanupSettings(deduplicate_paragraphs=True)
        )
    }
    
    # Dump the config to a dict
    # We use exclude_unset=False to ensure all default fields are included
    data = config.model_dump(exclude_none=True)
    
    # Write to file with some comments
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# ==============================================================================\n")
        f.write("# MASTER PIPELINE CONFIGURATION TEMPLATE\n")
        f.write("# ==============================================================================\n")
        f.write("# This template contains all possible configuration options and their default/\n")
        f.write("# expected structures. Use this as a reference when building custom configs.\n")
        f.write("# \n")
        f.write("# DO NOT MODIFY THIS FILE DIRECTLY. It is auto-generated.\n")
        f.write("# ==============================================================================\n\n")
        yaml.dump(data, f, sort_keys=False, default_flow_style=False)
        
    print(f"Master template successfully written to {output_path}")

if __name__ == "__main__":
    generate_master_config()
