import pytest

from src.core.interfaces import Chunk, SourceMetadata
from src.index.vectorstores import ChromaDBStore, QdrantStore, _deterministic_id


def _make_chunk(filename, chunk_index, text="hello world"):
    return Chunk(
        text=text,
        source_metadata=SourceMetadata(filename=filename, chunk_index=chunk_index, page_number=3),
        metadata={"level": "chunk"},
    )


def test_deterministic_id_is_stable_and_distinct():
    a = _make_chunk("book.pdf", 0)
    a_again = _make_chunk("book.pdf", 0, text="different text, same identity")
    b = _make_chunk("book.pdf", 1)

    assert _deterministic_id(a) == _deterministic_id(a_again)  # identity, not content, drives the id
    assert _deterministic_id(a) != _deterministic_id(b)


@pytest.mark.asyncio
async def test_chromadb_upsert_is_idempotent(tmp_path):
    """A prior bug minted a fresh uuid4() per chunk on every upsert, so
    re-indexing the same file duplicated all of its chunks. Re-upserting the
    same chunks should now overwrite in place instead of growing the
    collection."""
    store = ChromaDBStore(persist_directory=str(tmp_path / "chromadb"), collection_name="test")
    chunks = [_make_chunk("book.pdf", i) for i in range(3)]
    embeddings = [[0.1, 0.2, 0.3] for _ in chunks]

    await store.upsert(chunks, embeddings)
    assert store.collection.count() == 3

    await store.upsert(chunks, embeddings)  # re-index the same file
    assert store.collection.count() == 3


@pytest.mark.asyncio
async def test_chromadb_search_returns_matching_chunk(tmp_path):
    store = ChromaDBStore(persist_directory=str(tmp_path / "chromadb"), collection_name="test")
    chunk = _make_chunk("book.pdf", 0, text="the nosferatu clan hides in the sewers")
    await store.upsert([chunk], [[0.5, 0.5, 0.5]])

    results = await store.search([0.5, 0.5, 0.5], top_k=5)

    assert len(results) == 1
    assert results[0].text == "the nosferatu clan hides in the sewers"
    assert results[0].metadata["filename"] == "book.pdf"
    assert results[0].metadata["page_number"] == 3


def test_chromadb_is_duplicate_score_reads_distance_direction(tmp_path):
    store = ChromaDBStore(persist_directory=str(tmp_path / "chromadb"), collection_name="test")

    # Cosine distance = 1 - similarity, so a 0.99-similarity match is a
    # distance <= 0.01.
    assert store.is_duplicate_score(0.0, threshold=0.99) is True
    assert store.is_duplicate_score(0.01, threshold=0.99) is True
    assert store.is_duplicate_score(0.5, threshold=0.99) is False


def test_qdrant_is_duplicate_score_reads_similarity_direction(tmp_path):
    store = QdrantStore(path=str(tmp_path / "qdrant"), collection_name="test")

    # Qdrant reports cosine similarity directly - higher is closer.
    assert store.is_duplicate_score(1.0, threshold=0.99) is True
    assert store.is_duplicate_score(0.99, threshold=0.99) is True
    assert store.is_duplicate_score(0.5, threshold=0.99) is False
