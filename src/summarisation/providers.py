from typing import Optional
from ollama import AsyncClient
import google.generativeai as genai
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
        self.model_name = kwargs.get('model', 'gemini-1.5-flash')
        api_key = kwargs.get('api_key') or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be provided for GeminiSummariser")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.model_name)
        
    async def summarise(self, text: str, context: Optional[str] = None) -> str:
        prompt = f"Summarise the following text briefly.\n\n"
        if context:
            prompt += f"Context: {context}\n\n"
        prompt += f"Text to summarise: {text}\n\nSummary:"
        
        response = await self.model.generate_content_async(prompt)
        return response.text.strip()
