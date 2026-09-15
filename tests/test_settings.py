"""Regression tests for config strictness. Before this, an unknown or
misspelled key (e.g. the legacy `pipeline.mode`/`strip_regex` shape) was
silently dropped by Pydantic instead of raising, so a typo'd config just
quietly did nothing."""
import pytest
from pydantic import ValidationError

from src.config.settings import Config, load_config


def test_unknown_top_level_key_is_rejected():
    with pytest.raises(ValidationError):
        Config(pipeline={"mode": "extract_only"})


def test_unknown_nested_key_is_rejected():
    with pytest.raises(ValidationError):
        Config(cleanup_rules={"strip_regex": []})


def test_valid_minimal_config_still_loads():
    Config(file_rules={".txt": {"extractor": "MarkItDownExtractor"}})


@pytest.mark.parametrize("profile", [
    "config/config_template.yaml",
    "config/config_text_corpus.yaml",
    "config/config_pilot.yaml",
])
def test_real_profiles_still_load_under_strict_validation(profile):
    load_config(profile)
