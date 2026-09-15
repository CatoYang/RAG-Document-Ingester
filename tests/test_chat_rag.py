import pytest
import yaml

from src.chat.rag import NO_RESULTS_ANSWER, OllamaChatGenerator, RagAnswerer, build_messages
from src.core.interfaces import BaseEmbedder, SearchResult
from src.index.registry import EMBEDDER_REGISTRY
from src.index.vectorstores import ChromaDBStore


class _FakeEmbedder(BaseEmbedder):
    def __init__(self, **kwargs):
        self.embedded = []

    async def embed(self, texts):
        self.embedded.extend(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeVectorStore:
    def __init__(self, results):
        self._results = results
        self.last_top_k = None

    async def search(self, query_embedding, top_k=5):
        self.last_top_k = top_k
        return self._results[:top_k]


class _FakeGenerator:
    def __init__(self, pieces):
        self._pieces = pieces
        self.calls = []

    async def stream(self, messages):
        self.calls.append(messages)
        for piece in self._pieces:
            yield piece


RESULTS = [
    SearchResult(
        text="The Nosferatu are known for their hideous appearance.",
        metadata={"filename": "Nosferatu (revised).pdf", "page_number": 12, "section": "Overview"},
        score=0.12,
    ),
    SearchResult(
        text="Ahrimanes are bound to the spirits of the land.",
        metadata={"filename": "Ahrimanes.md"},
        score=0.34,
    ),
]


def test_prompt_numbers_chunks_with_file_and_page():
    system, user = build_messages("What do the Nosferatu look like?", RESULTS)

    assert system["role"] == "system"
    assert "ONLY" in system["content"] and "[1]" in system["content"]
    assert user["role"] == "user"
    assert "[1] (Nosferatu (revised).pdf, page 12, section: Overview)\nThe Nosferatu are known" in user["content"]
    assert "[2] (Ahrimanes.md, page unknown)\nAhrimanes are bound" in user["content"]
    assert user["content"].endswith("Question: What do the Nosferatu look like?")


@pytest.mark.asyncio
async def test_empty_retrieval_skips_generator():
    generator = _FakeGenerator(["should not be used"])
    answerer = RagAnswerer(_FakeEmbedder(), _FakeVectorStore([]), generator)

    result = await answerer.answer("anything")

    assert generator.calls == []
    assert result.answer == NO_RESULTS_ANSWER
    assert result.sources == []


@pytest.mark.asyncio
async def test_answer_carries_sources_and_generated_text():
    embedder = _FakeEmbedder()
    store = _FakeVectorStore(RESULTS)
    generator = _FakeGenerator(["They are ", "hideous [1]."])
    answerer = RagAnswerer(embedder, store, generator, top_k=2)

    result = await answerer.answer("What do the Nosferatu look like?")

    assert embedder.embedded == ["What do the Nosferatu look like?"]
    assert store.last_top_k == 2
    assert result.answer == "They are hideous [1]."
    assert result.sources == RESULTS
    assert generator.calls == [build_messages("What do the Nosferatu look like?", RESULTS)]


@pytest.fixture
def _register_fake_embedder():
    EMBEDDER_REGISTRY["_ChatFakeEmbedder"] = _FakeEmbedder
    yield
    del EMBEDDER_REGISTRY["_ChatFakeEmbedder"]


@pytest.mark.asyncio
async def test_from_config_reuses_indexing_stack_and_chat_settings(tmp_path, _register_fake_embedder):
    config = {
        "indexing": {
            "embedder": {"type": "_ChatFakeEmbedder"},
            "vectorstore": {
                "type": "ChromaDBStore",
                "params": {"persist_directory": str(tmp_path / "chroma"), "collection_name": "chat_test"},
            },
        },
        "chat": {"model": "mistral", "top_k": 3, "temperature": 0.0},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config))

    answerer = await RagAnswerer.from_config(str(config_path))

    assert isinstance(answerer.embedder, _FakeEmbedder)
    assert isinstance(answerer.vectorstore, ChromaDBStore)
    assert answerer.top_k == 3
    assert isinstance(answerer.generator, OllamaChatGenerator)
    assert answerer.generator.model == "mistral"
    assert answerer.generator.temperature == 0.0
    assert (await answerer.answer("anything")).answer == NO_RESULTS_ANSWER
