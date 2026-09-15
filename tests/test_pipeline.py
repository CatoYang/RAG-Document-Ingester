import pytest
import os
import yaml
from pathlib import Path
from src.pipeline import IngestionPipeline

@pytest.mark.asyncio
async def test_pipeline_idempotency(temp_workspace, mock_config):
    """Test that the pipeline correctly respects frontmatter and skips extraction."""
    # Create a dummy file that claims to have already completed extract and ocr
    staging_dir = temp_workspace["staging"]
    
    # Create the source file in raw/
    source_file = temp_workspace["raw"] / "test_doc.txt"
    with open(source_file, "w", encoding="utf-8") as f:
        f.write("Original content")
        
    # Create the staged file claiming phases are done
    staged_file = staging_dir / "test_doc.md"
    frontmatter = {
        "pipeline_phases": ["extract", "ocr"]
    }
    content = f"---\n{yaml.dump(frontmatter)}---\n\nExtracted content"
    
    with open(staged_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Run pipeline
    pipeline = IngestionPipeline(mock_config)
    await pipeline.process_file(str(source_file))
    
    # Verify that clean phase was added since it was missing
    with open(staged_file, "r", encoding="utf-8") as f:
        result = f.read()
        
    assert "clean" in result
    
    # Now verify that if it's already in output, it gets skipped entirely
    output_file = temp_workspace["output"] / "test_doc.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Output")
        
    # Clean the staged file
    os.remove(staged_file)
    
    # Run again
    await pipeline.process_file(str(source_file))
    
    # It should have skipped, so staging file should NOT be created
    assert not staged_file.exists()


@pytest.mark.asyncio
async def test_save_document_writes_real_newlines(temp_workspace, mock_config):
    """Frontmatter must be separated by real newlines, not the literal
    two-character sequence "\\n" (a prior bug wrote f"---\\n..." instead of
    f"---\\n..." with an actual escape, so every output file's frontmatter
    landed on one line)."""
    from src.core.interfaces import Document

    pipeline = IngestionPipeline(mock_config)
    doc = Document(source_file="test.md", content="Some body text", metadata={"pipeline_phases": ["extract"]})
    out_path = temp_workspace["staging"] / "newline_check.md"

    await pipeline._save_document(doc, out_path)

    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "\\n" not in content
    assert content.startswith("---\n")
    assert content.count("\n") >= 3


@pytest.mark.asyncio
async def test_ocr_failure_does_not_advance_pipeline_phase(temp_workspace, mock_config):
    """A failed OCR step must not be recorded as complete in pipeline_phases,
    or the file would be silently finalized without ever having been OCR'd."""
    mock_config.pipeline.steps.ocr.enabled = True
    mock_config.pipeline.steps.ocr.mode = "sync_live"  # stub mode - always reports failure

    staging_dir = temp_workspace["staging"]
    source_file = temp_workspace["raw"] / "ocr_fail_doc.txt"
    with open(source_file, "w", encoding="utf-8") as f:
        f.write("Original content")

    # Pre-stage a document that already completed "extract" and references an
    # image, so the OCR phase has something to attempt (and fail on, via the
    # sync_live stub) rather than short-circuiting on "no images found".
    (staging_dir / "pic.png").write_bytes(b"fake-image-bytes")
    staged_file = staging_dir / "ocr_fail_doc.md"
    frontmatter = {"pipeline_phases": ["extract"]}
    content = f"---\n{yaml.dump(frontmatter)}---\n\n![pic](pic.png)"
    with open(staged_file, "w", encoding="utf-8") as f:
        f.write(content)

    pipeline = IngestionPipeline(mock_config)
    await pipeline.process_file(str(source_file))

    output_file = temp_workspace["output"] / "ocr_fail_doc.md"

    with open(staged_file, "r", encoding="utf-8") as f:
        staged_content = f.read()

    assert "ocr" not in yaml.safe_load(staged_content.split("---")[1])["pipeline_phases"]
    assert not output_file.exists()
