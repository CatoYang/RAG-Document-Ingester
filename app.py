"""Streamlit chat over the indexed sourcebooks (TODO.md Path 5).

Each question is answered independently: retrieve top-k chunks, answer from
them only with [n] citations, and show the retrieved chunks under the answer.

Usage:
    streamlit run app.py -- config/<profile>.yaml
"""
import sys
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from src.chat.async_bridge import BackgroundLoop
from src.chat.rag import RagAnswerer
from src.core.interfaces import SearchResult

PROJECT_ROOT = Path(__file__).resolve().parent
USAGE = "streamlit run app.py -- config/<profile>.yaml"


@st.cache_resource
def get_loop() -> BackgroundLoop:
    return BackgroundLoop()


@st.cache_resource(show_spinner="Loading embedder and vector store...")
def get_answerer(config_path: str) -> RagAnswerer:
    return get_loop().run(RagAnswerer.from_config(config_path))


def resolve_config_path(argv: List[str]) -> Path:
    if len(argv) < 2:
        st.error(f"No config file given. Launch with: `{USAGE}`")
        st.stop()
    path = Path(argv[1])
    if not path.is_absolute() and not path.exists():
        path = PROJECT_ROOT / path
    if not path.is_file():
        st.error(f"Config file not found: `{path}`. Launch with: `{USAGE}`")
        st.stop()
    return path


def render_sources(sources: List[SearchResult], score_note: str) -> None:
    with st.expander(f"Retrieved chunks ({len(sources)})"):
        if not sources:
            st.write("No chunks were retrieved.")
            return
        st.caption(score_note)
        for rank, result in enumerate(sources, start=1):
            meta = result.metadata
            source = meta.get("filename") or meta.get("source") or "?"
            page = meta.get("page_number") or "-"
            section = meta.get("section") or "-"
            st.markdown(f"**[{rank}]** `{source}` | page {page} | section: {section} | score {result.score:.4f}")
            st.text(result.text)


def render_message(message: Dict[str, Any], score_note: str) -> None:
    with st.chat_message(message["role"]):
        if message.get("error"):
            st.error(message["content"])
        else:
            st.markdown(message["content"])
        if message["role"] == "assistant":
            render_sources(message["sources"], score_note)


def ask(answerer: RagAnswerer, question: str, score_note: str) -> Dict[str, Any]:
    loop = get_loop()
    try:
        with st.spinner("Searching the index..."):
            sources = loop.run(answerer.retrieve(question))
    except Exception as e:
        content = f"Retrieval failed. Is Ollama reachable via OLLAMA_HOST, with the embedding model pulled? ({type(e).__name__}: {e})"
        st.error(content)
        render_sources([], score_note)
        return {"role": "assistant", "content": content, "sources": [], "error": True}

    try:
        text = st.write_stream(loop.iterate(answerer.stream_answer(question, sources)))
    except Exception as e:
        content = f"Generation failed. Is Ollama reachable via OLLAMA_HOST, with the chat model pulled? ({type(e).__name__}: {e})"
        st.error(content)
        render_sources(sources, score_note)
        return {"role": "assistant", "content": content, "sources": sources, "error": True}

    render_sources(sources, score_note)
    return {"role": "assistant", "content": text if isinstance(text, str) else "".join(map(str, text)), "sources": sources}


def main() -> None:
    st.set_page_config(page_title="Sourcebook Q&A", layout="wide")
    st.title("Sourcebook Q&A")

    config_path = resolve_config_path(sys.argv)
    st.caption(f"Config: `{config_path}`. Each question is answered independently from the retrieved chunks.")

    try:
        answerer = get_answerer(str(config_path))
    except Exception as e:
        st.error(f"Could not initialise the embedder/vector store from `{config_path}`: {type(e).__name__}: {e}")
        st.stop()

    score_note = answerer.vectorstore.score_note

    messages: List[Dict[str, Any]] = st.session_state.setdefault("messages", [])
    for message in messages:
        render_message(message, score_note)

    question = st.chat_input("Ask about the indexed sourcebooks")
    if not question:
        return

    messages.append({"role": "user", "content": question})
    render_message(messages[-1], score_note)
    with st.chat_message("assistant"):
        messages.append(ask(answerer, question, score_note))


main()
