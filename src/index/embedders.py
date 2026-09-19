from typing import List
from ollama import AsyncClient
from rich.console import Console

from src.core.interfaces import BaseEmbedder

console = Console()


class OllamaEmbedder(BaseEmbedder):
    """Embeds text using a local Ollama model asynchronously."""

    def __init__(self, **kwargs):
        self.params = kwargs
        self.model = self.params.get('model', 'nomic-embed-text')
        # Without a timeout, ollama's httpx client waits forever if Ollama
        # stops responding - callers (e.g. Streamlit chat retrieval) hang
        # instead of surfacing an error.
        self.client = AsyncClient(timeout=self.params.get('timeout', 60.0))

    async def embed(self, texts: List[str]) -> List[List[float]]:
        console.print(
            f"[dim]Generating embeddings using Ollama ({self.model}) for {len(texts)} chunks...[/dim]")

        embeddings = []
        for text in texts:
            try:
                response = await self.client.embeddings(model=self.model, prompt=text)
                embeddings.append(response['embedding'])
            except Exception as e:
                console.print(f"[red]Error generating embedding: {e}[/red]")
                raise e

        return embeddings
