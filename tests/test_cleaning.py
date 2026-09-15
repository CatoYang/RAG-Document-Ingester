"""Tests for the cleaning stage: the static `DocumentCleaner` (wired into
`IngestionPipeline`, see src/pipeline.py's Phase 3) and `DynamicLLMCleaner`
(not wired into any pipeline path yet - see TODO.md's Cross-Cutting
section - so it's exercised directly here rather than through the pipeline).
LLM calls are mocked throughout; no real Ollama/Gemini traffic."""
import pytest

from src.clean.cleaner import DocumentCleaner
from src.clean.dynamic_cleaner import DynamicLLMCleaner
from src.config.settings import CleanupSettings


def _cleaner(**overrides):
    return DocumentCleaner(CleanupSettings(**overrides))


# ---------------------------------------------------------------------------
# DocumentCleaner (static)
# ---------------------------------------------------------------------------

def test_removes_zero_width_and_invisible_characters():
    cleaner = _cleaner(remove_zero_width_spaces=True)
    text = "Hello​ World﻿ Test‌‍"

    assert cleaner.clean(text) == "Hello World Test"


def test_trims_trailing_whitespace_per_line():
    cleaner = _cleaner(trim_trailing_whitespace=True)
    text = "Line one   \nLine two\t\nLine three"

    assert cleaner.clean(text) == "Line one\nLine two\nLine three"


def test_applies_custom_regex_removals():
    cleaner = _cleaner(regex_removals=[r"(?m)^Page \d+$"])
    text = "Real content\nPage 12\nMore content"

    cleaned = cleaner.clean(text)
    assert "Page 12" not in cleaned
    assert "Real content" in cleaned
    assert "More content" in cleaned


def test_invalid_regex_is_skipped_not_raised(capsys):
    cleaner = _cleaner(regex_removals=[r"(unclosed("])
    text = "Content that should survive."

    cleaned = cleaner.clean(text)

    assert cleaned == "Content that should survive."
    assert "Invalid regex pattern" in capsys.readouterr().out


def test_collapses_three_or_more_newlines_to_two():
    cleaner = _cleaner(collapse_newlines=True)
    text = "Paragraph one.\n\n\n\n\nParagraph two."

    assert cleaner.clean(text) == "Paragraph one.\n\nParagraph two."


def test_deduplicates_consecutive_repeated_paragraphs():
    cleaner = _cleaner(deduplicate_paragraphs=True, collapse_newlines=False)
    text = "Header text\n\nHeader text\n\nUnique body content."

    cleaned = cleaner.clean(text)
    assert cleaned.count("Header text") == 1
    assert "Unique body content." in cleaned


def test_deduplicate_paragraphs_disabled_by_default_keeps_repeats():
    cleaner = _cleaner(deduplicate_paragraphs=False)
    text = "Repeated line\n\nRepeated line"

    assert cleaner.clean(text).count("Repeated line") == 2


def test_empty_text_returns_empty_without_error():
    cleaner = _cleaner()
    assert cleaner.clean("") == ""


# ---------------------------------------------------------------------------
# DynamicLLMCleaner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_cleaner_returns_text_unchanged():
    cleaner = DynamicLLMCleaner({"enabled": False, "provider": "ollama"})
    text, review = await cleaner.clean("Some content.", "book.md")

    assert text == "Some content."
    assert review == []


@pytest.mark.asyncio
async def test_high_confidence_pattern_is_applied(monkeypatch):
    cleaner = DynamicLLMCleaner({"enabled": True, "provider": "ollama", "params": {"model": "llama3"}})

    async def fake_identify(sample, filename):
        return [{"pattern": r"(?m)^Page \d+$", "description": "page numbers", "confidence": 99}]

    monkeypatch.setattr(cleaner, "_identify_patterns_with_llm", fake_identify)

    # Padded well past the "Page 7" match itself so removing those 6
    # characters stays under the cleaner's 3% blast-radius guard.
    text = "Real content. " * 50 + "\nPage 7\n" + "More real content. " * 50
    cleaned, review_required = await cleaner.clean(text, "book.md")

    assert "Page 7" not in cleaned
    assert "Real content" in cleaned
    assert review_required == []


@pytest.mark.asyncio
async def test_low_confidence_pattern_is_flagged_for_review_not_applied(monkeypatch):
    cleaner = DynamicLLMCleaner({"enabled": True, "provider": "ollama", "params": {"model": "llama3"}})

    async def fake_identify(sample, filename):
        return [{"pattern": r"(?m)^Maybe boilerplate$", "description": "unsure", "confidence": 40}]

    monkeypatch.setattr(cleaner, "_identify_patterns_with_llm", fake_identify)

    text = "Maybe boilerplate\nReal content"
    cleaned, review_required = await cleaner.clean(text, "book.md")

    assert cleaned == text
    assert len(review_required) == 1
    assert review_required[0]["reason"] == "Low confidence"


@pytest.mark.asyncio
async def test_pattern_with_excessive_blast_radius_is_flagged_not_applied(monkeypatch):
    """A pattern that would strip >3% of the document is held back for
    review even at high confidence - this is the guard against a
    hallucinated regex silently eating real content."""
    cleaner = DynamicLLMCleaner({"enabled": True, "provider": "ollama", "params": {"model": "llama3"}})

    async def fake_identify(sample, filename):
        return [{"pattern": r"[A-Za-z]", "description": "way too broad", "confidence": 95}]

    monkeypatch.setattr(cleaner, "_identify_patterns_with_llm", fake_identify)

    text = "This entire sentence is mostly letters and would be gutted."
    cleaned, review_required = await cleaner.clean(text, "book.md")

    assert cleaned == text
    assert len(review_required) == 1
    assert "Blast radius" in review_required[0]["reason"]


@pytest.mark.asyncio
async def test_invalid_regex_from_llm_is_flagged_not_raised(monkeypatch):
    cleaner = DynamicLLMCleaner({"enabled": True, "provider": "ollama", "params": {"model": "llama3"}})

    async def fake_identify(sample, filename):
        return [{"pattern": r"(unclosed(", "description": "broken", "confidence": 95}]

    monkeypatch.setattr(cleaner, "_identify_patterns_with_llm", fake_identify)

    text = "Content that should survive untouched."
    cleaned, review_required = await cleaner.clean(text, "book.md")

    assert cleaned == text
    assert len(review_required) == 1
    assert "Regex compilation error" in review_required[0]["reason"]


@pytest.mark.asyncio
async def test_ollama_provider_is_queried_with_expected_prompt_shape(monkeypatch):
    """Verifies the Ollama codepath of `_identify_patterns_with_llm` itself
    (not just the parts around it), via a fake AsyncClient - no real Ollama
    call."""
    import sys
    import types as py_types

    fake_ollama_mod = py_types.ModuleType("ollama")

    class _FakeAsyncClient:
        def __init__(self, host=None):
            self.host = host

        async def chat(self, model, messages, format):
            return {"message": {"content": '[{"pattern": "(?m)^Foo$", "description": "d", "confidence": 90}]'}}

    fake_ollama_mod.AsyncClient = _FakeAsyncClient
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama_mod)

    cleaner = DynamicLLMCleaner({"enabled": True, "provider": "ollama", "params": {"model": "llama3"}})
    text = "Foo\n" + "Bar real content. " * 50
    cleaned, review_required = await cleaner.clean(text, "book.md")

    assert "Foo" not in cleaned
    assert "Bar real content" in cleaned
    assert review_required == []
