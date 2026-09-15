"""The Streamlit app caches the embedder/vector store/chat client across
reruns. Their async clients keep pooled connections bound to the event loop
they first ran on, so a fresh asyncio.run() per interaction breaks the second
call ("Event loop is closed"). These tests drive the real ollama.AsyncClient
against a local stub HTTP server (never a real Ollama) through BackgroundLoop,
and check that consecutive calls reuse one keep-alive connection."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Tuple

import pytest

from src.chat.async_bridge import BackgroundLoop
from src.chat.rag import OllamaChatGenerator
from src.index.embedders import OllamaEmbedder

CHAT_PARTS = ["Hel", "lo [1]", ""]


def start_stub_ollama() -> Tuple[ThreadingHTTPServer, List[Tuple[str, int]]]:
    requests: List[Tuple[str, int]] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            requests.append((self.path, self.client_address[1]))
            if self.path == "/api/embeddings":
                body = json.dumps({"embedding": [0.1, 0.2, 0.3]}) + "\n"
            else:
                body = "".join(
                    json.dumps({
                        "model": "llama3",
                        "created_at": "2026-09-16T00:00:00Z",
                        "message": {"role": "assistant", "content": part},
                        "done": i == len(CHAT_PARTS) - 1,
                    }) + "\n"
                    for i, part in enumerate(CHAT_PARTS)
                )
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, requests


@pytest.fixture
def stub_ollama(monkeypatch):
    server, requests = start_stub_ollama()
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{server.server_address[1]}")
    yield requests
    server.shutdown()
    server.server_close()


@pytest.fixture
def loop():
    background = BackgroundLoop()
    yield background
    background.close()


def test_consecutive_embed_calls_reuse_client_on_background_loop(stub_ollama, loop):
    embedder = OllamaEmbedder()

    first = loop.run(embedder.embed(["first question"]))
    second = loop.run(embedder.embed(["second question"]))

    assert first == second == [[0.1, 0.2, 0.3]]
    ports = [port for path, port in stub_ollama if path == "/api/embeddings"]
    assert len(ports) == 2 and len(set(ports)) == 1


def test_consecutive_streamed_chats_reuse_client_on_background_loop(stub_ollama, loop):
    generator = OllamaChatGenerator(model="llama3", temperature=0.1)
    messages = [{"role": "user", "content": "hi"}]

    first = "".join(loop.iterate(generator.stream(messages)))
    second = "".join(loop.iterate(generator.stream(messages)))

    assert first == second == "Hello [1]"
    ports = [port for path, port in stub_ollama if path == "/api/chat"]
    assert len(ports) == 2 and len(set(ports)) == 1


def test_iterate_closes_async_generator_when_consumer_stops_early(loop):
    closed = []

    async def numbers():
        try:
            for i in range(10):
                yield i
        finally:
            closed.append(True)

    iterator = loop.iterate(numbers())
    assert next(iterator) == 0
    iterator.close()

    assert closed == [True]
