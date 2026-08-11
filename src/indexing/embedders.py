from typing import List
import ollama
from rich.console import Console

from src.core.interfaces import BaseEmbedder

console = Console()

class OllamaEmbedder(BaseEmbedder):
    """Embeds text using a local Ollama model."""

    def __init__(self, **kwargs):
        self.params = kwargs
        self.model = self.params.get('model', 'nomic-embed-text')

    def embed(self, texts: List[str]) -> List[List[float]]:
        console.print(f"[dim]Generating embeddings using Ollama ({self.model}) for {len(texts)} chunks...[/dim]")
        
        embeddings = []
        for text in texts:
            try:
                response = ollama.embeddings(model=self.model, prompt=text)
                embeddings.append(response['embedding'])
            except Exception as e:
                console.print(f"[red]Error generating embedding: {e}[/red]")
                # Append an empty list or zeros in a production environment
                # Here we just raise to fail fast during dev
                raise e
                
        return embeddings
