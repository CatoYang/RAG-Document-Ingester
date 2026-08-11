from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional, Dict, Any

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
    metadata: Dict[str, Any]

class BaseChunker(ABC):
    """Abstract base class for all chunkers."""
    
    @abstractmethod
    def chunk(self, doc: Document) -> list[Chunk]:
        pass

class BaseEmbedder(ABC):
    """Abstract base class for all embedders."""
    
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        pass

class BaseVectorStore(ABC):
    """Abstract base class for all vector stores."""
    
    @abstractmethod
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]):
        pass

