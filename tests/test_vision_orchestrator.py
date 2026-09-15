import pytest
from types import SimpleNamespace

from src.core.interfaces import Document
from src.vision.orchestrator import _find_image_links, process_ocr


def test_find_image_links_handles_parentheses_in_path():
    """A non-greedy `(.*?)` capture truncates at the first ')' in the path,
    which happens whenever the source file's stem contains parentheses (e.g.
    "Toreador (revised).pdf" -> asset folder ".../Toreador (revised)/..."). We
    match greedily to the last ')' on the line instead."""
    text = "Some text\n\n![15_image_0.png](assets/Toreador (revised)/15_image_0.png)\n\nMore text"

    links = _find_image_links(text)

    assert len(links) == 1
    full_match, url = links[0]
    assert url == "assets/Toreador (revised)/15_image_0.png"
    assert full_match == "![15_image_0.png](assets/Toreador (revised)/15_image_0.png)"


def test_find_image_links_multiple_lines():
    text = "![a](one.png)\nsome text\n![b](two (2).png)\n"

    links = _find_image_links(text)

    assert [url for _, url in links] == ["one.png", "two (2).png"]


@pytest.mark.asyncio
async def test_process_ocr_passthrough_returns_completed(mock_config):
    doc = Document(source_file="test.md", content="no images here", metadata={})
    result = await process_ocr(doc, mock_config)
    assert result == "completed"


@pytest.mark.asyncio
async def test_process_ocr_no_images_returns_completed(mock_config, temp_workspace):
    mock_config.pipeline.steps.ocr.mode = "local_vlm"
    doc = Document(source_file="test.md", content="no image links in this document", metadata={})
    result = await process_ocr(doc, mock_config)
    assert result == "completed"


@pytest.mark.asyncio
async def test_process_ocr_sync_live_is_unimplemented_and_fails(mock_config, temp_workspace):
    """sync_live is a stub - it must report failure rather than silently
    claiming OCR completed, or the pipeline would permanently mark un-OCR'd
    documents as done."""
    mock_config.pipeline.steps.ocr.mode = "sync_live"
    (temp_workspace["staging"] / "img.png").write_bytes(b"fake-image-bytes")
    doc = Document(source_file="test.md", content="![img](img.png)", metadata={})
    result = await process_ocr(doc, mock_config)
    assert result == "failed"


@pytest.mark.asyncio
async def test_process_ocr_local_vlm_honours_ollama_host_env(mock_config, temp_workspace, monkeypatch):
    """local_vlm must not hardcode localhost - Ollama typically runs on the
    Windows host, not reachable from WSL as localhost."""
    mock_config.pipeline.steps.ocr.mode = "local_vlm"
    mock_config.pipeline.steps.ocr.model = "test-model"
    monkeypatch.setenv("OLLAMA_HOST", "http://192.0.2.10:11434")

    staging = temp_workspace["staging"]
    image_path = staging / "pic.png"
    image_path.write_bytes(b"fake-image-bytes")

    doc = Document(source_file="test.md", content="![pic](pic.png)", metadata={})

    called_urls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "transcribed text"}

    def fake_post(url, json):
        called_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr("requests.post", fake_post)

    result = await process_ocr(doc, mock_config)

    assert result == "completed"
    assert called_urls == ["http://192.0.2.10:11434/api/generate"]
    assert "transcribed text" in doc.content
