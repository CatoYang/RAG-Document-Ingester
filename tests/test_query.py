import pytest
from rich.console import Console

import query as query_module
from src.core.interfaces import SearchResult


class _FakeEmbedder:
    def __init__(self):
        self.embedded = []

    async def embed(self, texts):
        self.embedded.extend(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeVectorStore:
    def __init__(self, results):
        self._results = results
        self.last_query_embedding = None
        self.last_top_k = None

    async def search(self, query_embedding, top_k=5):
        self.last_query_embedding = query_embedding
        self.last_top_k = top_k
        return self._results[:top_k]


class _FakePipeline:
    def __init__(self, results):
        self.embedder = _FakeEmbedder()
        self.vectorstore = _FakeVectorStore(results)

    async def initialize(self, config_path):
        self.initialized_with = config_path


@pytest.mark.asyncio
async def test_run_embeds_searches_and_prints_results(monkeypatch, capsys):
    results = [
        SearchResult(
            text="The Nosferatu are known for their hideous appearance.",
            metadata={"filename": "Nosferatu (revised).pdf", "page_number": 12, "section": "Overview"},
            score=0.12,
        )
    ]
    fake_pipeline = _FakePipeline(results)
    monkeypatch.setattr(query_module, "IndexingPipeline", lambda: fake_pipeline)
    monkeypatch.setattr(query_module, "console", Console(width=200))  # avoid column-wrapping breaking substring checks

    await query_module.run("fake_config.yaml", "what do the nosferatu look like?", top_k=3)

    assert fake_pipeline.initialized_with == "fake_config.yaml"
    assert fake_pipeline.embedder.embedded == ["what do the nosferatu look like?"]
    assert fake_pipeline.vectorstore.last_query_embedding == [0.1, 0.2, 0.3]
    assert fake_pipeline.vectorstore.last_top_k == 3

    out = capsys.readouterr().out
    assert "Nosferatu (revised).pdf" in out
    assert "12" in out


@pytest.mark.asyncio
async def test_run_handles_no_results(monkeypatch, capsys):
    fake_pipeline = _FakePipeline([])
    monkeypatch.setattr(query_module, "IndexingPipeline", lambda: fake_pipeline)

    await query_module.run("fake_config.yaml", "anything", top_k=5)

    out = capsys.readouterr().out
    assert "No results" in out
