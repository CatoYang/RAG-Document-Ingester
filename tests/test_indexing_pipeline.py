"""Integration test for the full chunk -> embed -> upsert flow driven by
`IndexingPipeline` itself (as opposed to test_vectorstores.py, which drives
`ChromaDBStore` directly, or test_chunkers.py, which drives `MarkdownChunker`
directly). Only the embedder is faked, since a real one needs Ollama
running; the chunker and vector store are the real classes running against
a tmp_path ChromaDB, so this exercises the actual wiring `IndexingPipeline`
does between them - including that re-running indexing is idempotent
end-to-end through the pipeline, not just at the vectorstore layer."""
import pytest
import yaml

from src.index.pipeline import IndexingPipeline
from src.index.registry import EMBEDDER_REGISTRY
from src.core.interfaces import BaseEmbedder


class _FakeEmbedder(BaseEmbedder):
    """Deterministic, network-free stand-in for OllamaEmbedder: a fixed-size
    vector derived from each text's length, just distinct enough per-input
    to prove real per-chunk texts reached here."""

    def __init__(self, **kwargs):
        self.embedded_texts = []

    async def embed(self, texts):
        self.embedded_texts.extend(texts)
        return [[float(len(t) % 7), 0.0, 1.0] for t in texts]


@pytest.fixture(autouse=True)
def _register_fake_embedder():
    EMBEDDER_REGISTRY["_FakeEmbedder"] = _FakeEmbedder
    yield
    del EMBEDDER_REGISTRY["_FakeEmbedder"]


def _write_config(tmp_path, chroma_dir):
    config = {
        "indexing": {
            "enabled": True,
            "chunker": {"type": "MarkdownChunker", "params": {"chunk_size": 1000, "chunk_overlap": 0}},
            "embedder": {"type": "_FakeEmbedder", "params": {}},
            "vectorstore": {
                "type": "ChromaDBStore",
                "params": {"persist_directory": str(chroma_dir), "collection_name": "test_indexing"},
            },
        },
        "summarisation": {"enabled": False, "provider": "ollama"},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config))
    return config_path


@pytest.mark.asyncio
async def test_process_directory_chunks_embeds_and_upserts_every_file(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "book_one.md").write_text("# Chapter One\n\nContent about vampires and clans.")
    (output_dir / "book_two.md").write_text("# Chapter Two\n\nContent about dragonmarks and houses.")

    config_path = _write_config(tmp_path, tmp_path / "chromadb")

    pipeline = IndexingPipeline()
    await pipeline.initialize(str(config_path))
    await pipeline.process_directory(str(output_dir))

    assert pipeline.vectorstore.collection.count() == 2
    embedded = pipeline.embedder.embedded_texts
    assert any("vampires and clans" in t for t in embedded)
    assert any("dragonmarks and houses" in t for t in embedded)


@pytest.mark.asyncio
async def test_reindexing_the_same_directory_is_idempotent(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "book_one.md").write_text("# Chapter One\n\nContent about vampires and clans.")

    config_path = _write_config(tmp_path, tmp_path / "chromadb")

    pipeline = IndexingPipeline()
    await pipeline.initialize(str(config_path))
    await pipeline.process_directory(str(output_dir))
    assert pipeline.vectorstore.collection.count() == 1

    # Re-running indexing (e.g. a second `python main.py` invocation) must
    # overwrite in place, not duplicate - the deterministic-ID fix in
    # src/index/vectorstores.py, exercised here through the whole pipeline.
    await pipeline.process_directory(str(output_dir))
    assert pipeline.vectorstore.collection.count() == 1


@pytest.mark.asyncio
async def test_frontmatter_is_parsed_into_metadata_not_embedded(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "book_one.md").write_text(
        "---\npipeline_phases:\n  - extract\n  - clean\n---\n\n# Title\n\nReal body content."
    )

    config_path = _write_config(tmp_path, tmp_path / "chromadb")

    pipeline = IndexingPipeline()
    await pipeline.initialize(str(config_path))
    await pipeline.process_directory(str(output_dir))

    assert pipeline.vectorstore.collection.count() == 1
    embedded_text = pipeline.embedder.embedded_texts[0]
    assert "pipeline_phases" not in embedded_text
    assert "Real body content." in embedded_text
