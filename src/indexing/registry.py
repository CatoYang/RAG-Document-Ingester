from typing import Type

from src.core.interfaces import BaseChunker, BaseEmbedder, BaseVectorStore
from src.indexing.chunkers import MarkdownChunker
from src.indexing.embedders import OllamaEmbedder
from src.indexing.vectorstores import ChromaDBStore, QdrantStore

CHUNKER_REGISTRY = {
    "MarkdownChunker": MarkdownChunker,
}

EMBEDDER_REGISTRY = {
    "OllamaEmbedder": OllamaEmbedder,
}

VECTORSTORE_REGISTRY = {
    "ChromaDBStore": ChromaDBStore,
    "QdrantStore": QdrantStore,
}


def get_chunker_class(name: str) -> Type[BaseChunker]:
    if name not in CHUNKER_REGISTRY:
        raise ValueError(f"Chunker '{name}' not found in registry.")
    return CHUNKER_REGISTRY[name]


def get_embedder_class(name: str) -> Type[BaseEmbedder]:
    if name not in EMBEDDER_REGISTRY:
        raise ValueError(f"Embedder '{name}' not found in registry.")
    return EMBEDDER_REGISTRY[name]


def get_vectorstore_class(name: str) -> Type[BaseVectorStore]:
    if name not in VECTORSTORE_REGISTRY:
        raise ValueError(f"VectorStore '{name}' not found in registry.")
    return VECTORSTORE_REGISTRY[name]
