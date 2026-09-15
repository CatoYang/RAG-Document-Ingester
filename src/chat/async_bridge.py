import asyncio
import threading
from typing import AsyncIterator, Awaitable, Coroutine, Iterator, Any, TypeVar

T = TypeVar("T")


class BackgroundLoop:
    """Runs coroutines on one long-lived event loop in a daemon thread.

    Async clients (ollama.AsyncClient, AsyncQdrantClient) hold httpx/httpcore
    connection pools bound to the loop they first ran on, so objects cached
    across Streamlit reruns must always be driven from the same loop rather
    than a fresh asyncio.run() per interaction."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def iterate(self, agen: AsyncIterator[T]) -> Iterator[T]:
        async def _await(awaitable: Awaitable[Any]) -> Any:
            return await awaitable

        try:
            while True:
                try:
                    yield self.run(_await(agen.__anext__()))
                except StopAsyncIteration:
                    return
        finally:
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                self.run(_await(aclose()))

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()
