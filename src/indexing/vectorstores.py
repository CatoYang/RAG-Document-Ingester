import uuid
import asyncio
from typing import List
import chromadb
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from rich.console import Console

from src.core.interfaces import BaseVectorStore, Chunk

console = Console()


class ChromaDBStore(BaseVectorStore):
    """Local vector store using ChromaDB."""

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
        self.collection = self.client.get_or_create_collection(
            name=collection_name)

    async def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        console.print(
            f"[dim]Upserting {len(chunks)} chunks into ChromaDB...[/dim]")

        ids = [str(uuid.uuid4()) for _ in chunks]
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


class QdrantStore(BaseVectorStore):
    """Vector store using Qdrant asynchronously."""

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
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={"text": chunk.text, **meta}
                )
            )

        await self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
