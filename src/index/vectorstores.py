import uuid
import asyncio
from typing import List
import chromadb
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from rich.console import Console

from src.core.interfaces import BaseVectorStore, Chunk, SearchResult

console = Console()


def _deterministic_id(chunk: Chunk) -> str:
    """Derives a stable point ID from a chunk's identity (filename + level +
    section + chunk_index) so re-running indexing on the same content
    upserts (overwrites) existing vectors instead of duplicating them - the
    prior implementation minted a fresh uuid4() per call, so every re-index
    of the same file duplicated all of its chunks in the vector store.

    Uses uuid5 rather than a plain hash digest because Qdrant point IDs must
    be an unsigned int or a valid UUID string."""
    key = "|".join([
        chunk.source_metadata.filename,
        str(chunk.metadata.get("level", "chunk")),
        str(chunk.source_metadata.section or ""),
        str(chunk.source_metadata.chunk_index),
    ])
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


class ChromaDBStore(BaseVectorStore):
    """Local vector store using ChromaDB."""

    score_note = "Score is ChromaDB's distance: lower is closer."

    def __init__(self, **kwargs):
        self.params = kwargs
        persist_dir = self.params.get('persist_directory', 'data/chromadb')

        from pathlib import Path
        persist_path = Path(persist_dir)
        if not persist_path.is_absolute():
            project_root = Path(__file__).resolve().parent.parent.parent
            persist_path = project_root / persist_path

        collection_name = self.params.get(
            'collection_name', 'default_collection')

        self.client = chromadb.PersistentClient(path=str(persist_path))
        # Without this, Chroma defaults new collections to L2 distance on
        # unnormalised vectors, which can rank differently than cosine
        # similarity (the metric QdrantStore uses). Only takes effect on
        # collection creation - an existing collection keeps whatever space
        # it was created with, so switching this requires a re-index.
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"})

    async def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        console.print(
            f"[dim]Upserting {len(chunks)} chunks into ChromaDB...[/dim]")

        ids = [_deterministic_id(chunk) for chunk in chunks]
        texts = [chunk.text for chunk in chunks]
        metadatas = []

        for chunk in chunks:
            # Merge source_metadata and metadata for storage
            meta = chunk.metadata.copy()
            meta.update(chunk.source_metadata.model_dump(exclude_none=True))

            # ChromaDB requires all metadata values to be str, int, float, or
            # bool
            for k, v in list(meta.items()):
                if not isinstance(v, (str, int, float, bool)):
                    meta[k] = str(v)
            metadatas.append(meta)

        def _do_upsert():
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )

        await asyncio.to_thread(_do_upsert)

    async def search(self, query_embedding: List[float], top_k: int = 5) -> List[SearchResult]:
        def _do_query():
            return self.collection.query(query_embeddings=[query_embedding], n_results=top_k)

        result = await asyncio.to_thread(_do_query)

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        # ChromaDB reports a distance (lower = more similar), not a
        # similarity score - see SearchResult's docstring.
        return [
            SearchResult(text=doc, metadata=meta or {}, score=dist)
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]

    def is_duplicate_score(self, score: float, threshold: float) -> bool:
        # Cosine distance = 1 - cosine similarity, so a `threshold` (e.g.
        # 0.99) similarity match is a distance <= 1 - threshold. Only
        # meaningful for a cosine-space collection (see the hnsw:space fix
        # above) - meaningless against an existing L2 collection.
        return score <= (1.0 - threshold)


class QdrantStore(BaseVectorStore):
    """Vector store using Qdrant asynchronously."""

    score_note = "Score is Qdrant's cosine similarity: higher is closer."

    def __init__(self, **kwargs):
        self.params = kwargs

        url = self.params.get('url', None)
        path = self.params.get('path', None)
        api_key = self.params.get('api_key', None)
        self.collection_name = self.params.get(
            'collection_name', 'default_collection')

        if path:
            from pathlib import Path
            qdrant_path = Path(path)
            if not qdrant_path.is_absolute():
                project_root = Path(__file__).resolve().parent.parent.parent
                qdrant_path = project_root / qdrant_path
            self.client = AsyncQdrantClient(path=str(qdrant_path))
        else:
            self.client = AsyncQdrantClient(
                url=url or 'http://localhost:6333', api_key=api_key)

        self.vector_size = self.params.get('vector_size', 768)

    async def _ensure_collection(self):
        exists = await self.client.collection_exists(self.collection_name)
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    async def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        await self._ensure_collection()
        console.print(
            f"[dim]Upserting {len(chunks)} chunks into Qdrant...[/dim]")

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            meta = chunk.metadata.copy()
            meta.update(chunk.source_metadata.model_dump(exclude_none=True))

            points.append(
                PointStruct(
                    id=_deterministic_id(chunk),
                    vector=embedding,
                    payload={"text": chunk.text, **meta}
                )
            )

        await self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    async def search(self, query_embedding: List[float], top_k: int = 5) -> List[SearchResult]:
        await self._ensure_collection()
        hits = await self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
        )

        results = []
        for hit in hits:
            payload = dict(hit.payload or {})
            text = payload.pop("text", "")
            results.append(SearchResult(text=text, metadata=payload, score=hit.score))
        return results

    def is_duplicate_score(self, score: float, threshold: float) -> bool:
        # Qdrant reports cosine similarity directly - higher is closer.
        return score >= threshold
