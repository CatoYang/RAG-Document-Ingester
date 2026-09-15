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
