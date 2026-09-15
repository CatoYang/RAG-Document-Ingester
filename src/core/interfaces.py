from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class SourceMetadata(BaseModel):
    """Metadata representing the source of a chunk."""
    filename: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_index: int


class Document(BaseModel):
    """Data model representing a parsed document."""
    source_file: str
    content: str
    metadata: Dict[str, Any]


class BaseExtractor(ABC):
    """Abstract base class for all document extractors."""

    @abstractmethod
    def extract(self, file_path: str, **kwargs) -> Document:
        """
        Extracts content from a file and returns a Document object.

        Args:
            file_path: The path to the file to parse.
            **kwargs: Additional parameters for the extractor.

        Returns:
            Document: The extracted content and metadata.
        """
        pass


class BaseRouter(ABC):
    """Abstract base class for routing documents to extractors."""

    @abstractmethod
    def get_extractor(self, file_path: str) -> BaseExtractor:
        """
        Determines the appropriate extractor for the given file.

        Args:
            file_path: The path to the file to route.

        Returns:
            BaseExtractor: An instance of the appropriate extractor.
        """
        pass


class Chunk(BaseModel):
    """Data model representing a chunk of text."""
    text: str
    source_metadata: SourceMetadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseChunker(ABC):
    """Abstract base class for all chunkers."""

    @abstractmethod
    async def chunk(self, doc: Document) -> List[Chunk]:
        pass


class BaseEmbedder(ABC):
    """Abstract base class for all embedders."""

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        pass


class SearchResult(BaseModel):
    """A single retrieval hit: the matched chunk text plus its stored
    metadata and a similarity score (interpretation - higher is more similar
    - is left to the caller; different stores use different distance
    metrics, and this project doesn't yet normalize across them)."""
    text: str
    metadata: Dict[str, Any]
    score: float


class BaseVectorStore(ABC):
    """Abstract base class for all vector stores."""

    @abstractmethod
    async def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        pass

    @abstractmethod
    async def search(self, query_embedding: List[float], top_k: int = 5) -> List["SearchResult"]:
        """Returns the `top_k` chunks most similar to `query_embedding`."""
        pass


class BaseSummariser(ABC):
    """Abstract base class for interchangeable LLM summarisation providers."""

    @abstractmethod
    async def summarise(self, text: str, context: Optional[str] = None) -> str:
        """
        Summarises the given text.

        Args:
            text: The text to summarise.
            context: Optional context to guide the summarisation.

        Returns:
            str: The generated summary.
        """
        pass
