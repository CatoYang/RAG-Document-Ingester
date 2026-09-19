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

    #: Human-readable note on how to read `SearchResult.score` for this
    #: store, since the direction (lower vs. higher is closer) differs by
    #: store/metric. Overridden per subclass.
    score_note: str = "Score is the vector store's raw value; direction of 'closer' is store-specific."

    @abstractmethod
    async def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        pass

    @abstractmethod
    async def search(self, query_embedding: List[float], top_k: int = 5) -> List["SearchResult"]:
        """Returns the `top_k` chunks most similar to `query_embedding`."""
        pass

    @abstractmethod
    def is_duplicate_score(self, score: float, threshold: float) -> bool:
        """Whether a `SearchResult.score` from this store represents a match
        at least as close as `threshold` (0-1 similarity). Centralizes the
        per-store score direction (see `score_note`) so callers never have
        to know whether lower or higher is closer."""
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
