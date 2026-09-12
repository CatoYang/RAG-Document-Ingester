from typing import Optional
from ollama import AsyncClient
from google import genai
import os

from src.core.interfaces import BaseSummariser


class OllamaSummariser(BaseSummariser):
    def __init__(self, **kwargs):
        self.model = kwargs.get('model', 'llama3')
        self.client = AsyncClient()

    async def summarise(self, text: str, context: Optional[str] = None) -> str:
        prompt = f"Summarise the following text briefly.\n\n"
        if context:
            prompt += f"Context: {context}\n\n"
        prompt += f"Text to summarise: {text}\n\nSummary:"

        response = await self.client.generate(model=self.model, prompt=prompt)
        return response['response'].strip()


class GeminiSummariser(BaseSummariser):
    def __init__(self, **kwargs):
        self.model_name = kwargs.get('model', 'gemini-3.6-flash')
        api_key = kwargs.get('api_key') or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY must be provided for GeminiSummariser")

        self.client = genai.Client(api_key=api_key)

    async def summarise(self, text: str, context: Optional[str] = None) -> str:
        prompt = "Summarise the following text briefly.

"
        if context:
            prompt += f"Context: {context}

"
        prompt += f"Text to summarise: {text}

Summary:"

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        return response.text.strip()