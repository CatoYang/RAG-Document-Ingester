import pytest
from rich.console import Console

import eval_golden as eval_module
from src.core.interfaces import SearchResult


class _FakeEmbedder:
    async def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeVectorStore:
    def __init__(self, results):
        self._results = results

    async def search(self, query_embedding, top_k=5):
        return self._results[:top_k]


class _FakePipeline:
    def __init__(self, results):
        self.embedder = _FakeEmbedder()
        self.vectorstore = _FakeVectorStore(results)

    async def initialize(self, config_path):
        pass


@pytest.mark.asyncio
async def test_recall_counts_hit_within_page_tolerance(tmp_path, monkeypatch, capsys):
    qa_path = tmp_path / "golden_qa.yaml"
    qa_path.write_text(
        "questions:\n"
        "  - question: \"What is the Nosferatu clan's weakness?\"\n"
        "    expected_source: \"Nosferatu (revised).pdf\"\n"
        "    expected_page: 10\n"
    )

    results = [SearchResult(text="hideous appearance", metadata={"filename": "Nosferatu (revised).pdf", "page_number": 11}, score=0.1)]
    fake_pipeline = _FakePipeline(results)
    monkeypatch.setattr(eval_module, "IndexingPipeline", lambda: fake_pipeline)
    monkeypatch.setattr(eval_module, "console", Console(width=200))

    await eval_module.run("fake_config.yaml", str(qa_path), top_k=5, page_tolerance=2)

    out = capsys.readouterr().out
    assert "Recall@5: 1/1 (100%)" in out


@pytest.mark.asyncio
async def test_recall_counts_miss_outside_page_tolerance(tmp_path, monkeypatch, capsys):
    qa_path = tmp_path / "golden_qa.yaml"
    qa_path.write_text(
        "questions:\n"
        "  - question: \"What is the Nosferatu clan's weakness?\"\n"
        "    expected_source: \"Nosferatu (revised).pdf\"\n"
        "    expected_page: 10\n"
    )

    # Right book, page far outside tolerance
    results = [SearchResult(text="unrelated content", metadata={"filename": "Nosferatu (revised).pdf", "page_number": 90}, score=0.1)]
    fake_pipeline = _FakePipeline(results)
    monkeypatch.setattr(eval_module, "IndexingPipeline", lambda: fake_pipeline)
    monkeypatch.setattr(eval_module, "console", Console(width=200))

    await eval_module.run("fake_config.yaml", str(qa_path), top_k=5, page_tolerance=2)

    out = capsys.readouterr().out
    assert "Recall@5: 0/1 (0%)" in out


@pytest.mark.asyncio
async def test_recall_counts_miss_wrong_source(tmp_path, monkeypatch, capsys):
    qa_path = tmp_path / "golden_qa.yaml"
    qa_path.write_text(
        "questions:\n"
        "  - question: \"What is the Nosferatu clan's weakness?\"\n"
        "    expected_source: \"Nosferatu (revised).pdf\"\n"
        "    expected_page: null\n"
    )

    results = [SearchResult(text="unrelated content", metadata={"filename": "Toreador (revised).pdf", "page_number": 5}, score=0.1)]
    fake_pipeline = _FakePipeline(results)
    monkeypatch.setattr(eval_module, "IndexingPipeline", lambda: fake_pipeline)
    monkeypatch.setattr(eval_module, "console", Console(width=200))

    await eval_module.run("fake_config.yaml", str(qa_path), top_k=5, page_tolerance=2)

    out = capsys.readouterr().out
    assert "Recall@5: 0/1 (0%)" in out
