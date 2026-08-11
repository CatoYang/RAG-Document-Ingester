import uuid
from typing import List
import chromadb
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from rich.console import Console

from src.core.interfaces import BaseVectorStore, Chunk

console = Console()

class ChromaDBStore(BaseVectorStore):
    """Local vector store using ChromaDB."""

    def __init__(self, **kwargs):
        self.params = kwargs
        persist_dir = self.params.get('persist_directory', 'data/chromadb')
        collection_name = self.params.get('collection_name', 'default_collection')
        
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        console.print(f"[dim]Upserting {len(chunks)} chunks into ChromaDB...[/dim]")
        
        ids = [str(uuid.uuid4()) for _ in chunks]
        texts = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        
        # ChromaDB requires all metadata values to be str, int, float, or bool
        for meta in metadatas:
            for k, v in list(meta.items()):
                if not isinstance(v, (str, int, float, bool)):
                    meta[k] = str(v)
                    
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )


class QdrantStore(BaseVectorStore):
    """Vector store using Qdrant (typically via Docker/server)."""

    def __init__(self, **kwargs):
        self.params = kwargs
        
        url = self.params.get('url', 'http://localhost:6333')
        api_key = self.params.get('api_key', None)
        self.collection_name = self.params.get('collection_name', 'default_collection')
        
        self.client = QdrantClient(url=url, api_key=api_key)
        
        # We need to ensure the collection exists. If it doesn't, we need the vector size.
        # But Qdrant client allows checking if collection exists.
        vector_size = self.params.get('vector_size', 768) # Default for nomic-embed-text
        
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        console.print(f"[dim]Upserting {len(chunks)} chunks into Qdrant...[/dim]")
        
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={"text": chunk.text, **chunk.metadata}
                )
            )
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
