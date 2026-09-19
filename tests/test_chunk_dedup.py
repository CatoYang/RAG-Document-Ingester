"""Unit tests for IndexingPipeline's opt-in chunk-level near-duplicate check
(TODO.md Path 2: "Vector DB cosine similarity check"). Drives
`_drop_near_duplicate_chunks` directly against a real (tmp_path) cosine
ChromaDBStore, since that's the whole surface this feature touches - no need
to go through the full chunk/embed/upsert pipeline for these cases."""
import pytest

from src.config.settings import ChunkDedupSettings
from src.core.interfaces import Chunk, SourceMetadata
from src.index.pipeline import IndexingPipeline
from src.index.vectorstores import ChromaDBStore


def _chunk(filename, index, text="text"):
    return Chunk(
        text=text,
        source_metadata=SourceMetadata(filename=filename, chunk_index=index),
        metadata={},
    )


def _pipeline_with_store(store, threshold=0.99):
    pipeline = IndexingPipeline()
    pipeline.vectorstore = store
    pipeline.chunk_dedup = ChunkDedupSettings(enabled=True, threshold=threshold)
    return pipeline


@pytest.mark.asyncio
async def test_drops_near_duplicate_chunk_from_a_different_file(tmp_path):
    store = ChromaDBStore(persist_directory=str(tmp_path / "chromadb"), collection_name="test")
    await store.upsert([_chunk("BookA.md", 0, "boilerplate legal text")], [[1.0, 0.0, 0.0]])

    pipeline = _pipeline_with_store(store)
    duplicate_chunk = _chunk("BookB.md", 0, "same boilerplate legal text, different book")
    distinct_chunk = _chunk("BookB.md", 1, "an actual unique paragraph about dragonmarks")

    kept_chunks, kept_embeddings = await pipeline._drop_near_duplicate_chunks(
        [duplicate_chunk, distinct_chunk],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )

    assert [c.source_metadata.chunk_index for c in kept_chunks] == [1]
    assert kept_embeddings == [[0.0, 1.0, 0.0]]


@pytest.mark.asyncio
async def test_never_drops_a_same_file_match(tmp_path):
    store = ChromaDBStore(persist_directory=str(tmp_path / "chromadb"), collection_name="test")
    await store.upsert([_chunk("BookA.md", 0, "some paragraph")], [[1.0, 0.0, 0.0]])

    pipeline = _pipeline_with_store(store)
    # Re-processing BookA.md's own chunk (e.g. a plain re-index) must never
    # be treated as a duplicate to drop - it's an idempotent overwrite of
    # the same deterministic chunk ID, not a cross-document duplicate.
    same_file_chunk = _chunk("BookA.md", 0, "some paragraph")

    kept_chunks, kept_embeddings = await pipeline._drop_near_duplicate_chunks(
        [same_file_chunk], [[1.0, 0.0, 0.0]]
    )

    assert len(kept_chunks) == 1
    assert kept_embeddings == [[1.0, 0.0, 0.0]]


@pytest.mark.asyncio
async def test_keeps_chunks_below_the_similarity_threshold(tmp_path):
    store = ChromaDBStore(persist_directory=str(tmp_path / "chromadb"), collection_name="test")
    await store.upsert([_chunk("BookA.md", 0, "some paragraph")], [[1.0, 0.0, 0.0]])

    pipeline = _pipeline_with_store(store, threshold=0.99)
    unrelated_chunk = _chunk("BookB.md", 0, "a completely different topic")

    kept_chunks, _ = await pipeline._drop_near_duplicate_chunks(
        [unrelated_chunk], [[0.0, 1.0, 0.0]]
    )

    assert len(kept_chunks) == 1
