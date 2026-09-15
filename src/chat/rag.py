from typing import Any, AsyncIterator, Dict, List, Optional, Protocol

from ollama import AsyncClient
from pydantic import BaseModel

from src.config.settings import load_config
from src.core.interfaces import BaseEmbedder, BaseVectorStore, SearchResult
from src.index.pipeline import IndexingPipeline

NO_RESULTS_ANSWER = (
    "Nothing relevant was found in the indexed sourcebooks for this question, "
    "so there is nothing to answer from. Has anything been indexed into this vector store yet?"
)

SYSTEM_PROMPT = """You answer questions about tabletop RPG sourcebooks using ONLY the numbered context passages you are given.

Rules:
- Use only information stated in the context passages. Do not use outside knowledge, even if you think you know the answer.
- Cite the passages that support each statement with their numbers in square brackets, e.g. [1] or [2][3].
- If the passages do not contain the answer, say plainly that the retrieved passages don't cover it. Do not guess.
- If the passages only partly answer the question, answer that part, cite it, and say what is missing."""

Message = Dict[str, str]


class ChatAnswer(BaseModel):
    question: str
    answer: str
    sources: List[SearchResult]


class ChatGenerator(Protocol):
    def stream(self, messages: List[Message]) -> AsyncIterator[str]: ...


class OllamaChatGenerator:
    """Streams a chat completion from Ollama. The host comes from
    `OLLAMA_HOST` unless given explicitly."""

    def __init__(self, model: str, temperature: float, host: Optional[str] = None) -> None:
        self.model = model
        self.temperature = temperature
        self.client = AsyncClient(host=host)

    async def stream(self, messages: List[Message]) -> AsyncIterator[str]:
        response = await self.client.chat(
            model=self.model,
            messages=messages,
            stream=True,
            options={"temperature": self.temperature},
        )
        async for part in response:
            if part.message.content:
                yield part.message.content


def describe_source(metadata: Dict[str, Any]) -> str:
    parts = [str(metadata.get("filename") or metadata.get("source") or "unknown file")]
    page = metadata.get("page_number")
    parts.append(f"page {page}" if page not in (None, "") else "page unknown")
    if metadata.get("section"):
        parts.append(f"section: {metadata['section']}")
    if metadata.get("level") in ("document", "section"):
        parts.append(f"{metadata['level']} summary")
    return ", ".join(parts)


def build_messages(question: str, sources: List[SearchResult]) -> List[Message]:
    blocks = [
        f"[{i}] ({describe_source(r.metadata)})\n{r.text.strip()}"
        for i, r in enumerate(sources, start=1)
    ]
    user = "Context passages:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


class RagAnswerer:
    def __init__(
        self,
        embedder: BaseEmbedder,
        vectorstore: BaseVectorStore,
        generator: ChatGenerator,
        top_k: int = 5,
    ) -> None:
        self.embedder = embedder
        self.vectorstore = vectorstore
        self.generator = generator
        self.top_k = top_k

    @classmethod
    async def from_config(cls, config_path: str) -> "RagAnswerer":
        chat = load_config(config_path).chat
        pipeline = IndexingPipeline()
        await pipeline.initialize(config_path)
        generator = OllamaChatGenerator(model=chat.model, temperature=chat.temperature)
        return cls(pipeline.embedder, pipeline.vectorstore, generator, top_k=chat.top_k)

    async def retrieve(self, question: str) -> List[SearchResult]:
        embeddings = await self.embedder.embed([question])
        return await self.vectorstore.search(embeddings[0], top_k=self.top_k)

    async def stream_answer(self, question: str, sources: List[SearchResult]) -> AsyncIterator[str]:
        if not sources:
            yield NO_RESULTS_ANSWER
            return
        async for piece in self.generator.stream(build_messages(question, sources)):
            yield piece

    async def answer(self, question: str) -> ChatAnswer:
        sources = await self.retrieve(question)
        pieces = [piece async for piece in self.stream_answer(question, sources)]
        return ChatAnswer(question=question, answer="".join(pieces), sources=sources)
