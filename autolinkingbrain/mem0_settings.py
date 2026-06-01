"""Общие настройки Mem0/Chroma для brain_server.py и viewer.py — коллекция и путь должны совпадать."""

import os
from pathlib import Path

from autolinkingbrain.paths import REPO_ROOT

_DEFAULT_CHROMA_DIR = REPO_ROOT / "chroma_data"

# Каталог Chroma на диске. Для прежней базы укажите: MEM0_CHROMA_PATH=D:\MemoDb
DB_PATH = os.environ.get("MEM0_CHROMA_PATH", str(_DEFAULT_CHROMA_DIR))

CHROMA_COLLECTION = os.environ.get("MEM0_CHROMA_COLLECTION", "graph_brain")
OLLAMA_LLM = os.environ.get("OLLAMA_LLM", "llama3.2")
OLLAMA_EMBED = os.environ.get("OLLAMA_EMBED", "nomic-embed-text")


def chroma_path_resolved() -> Path:
    """Абсолютный путь к каталогу Chroma (для UI и отладки)."""
    return Path(DB_PATH).expanduser().resolve()


def mem0_vector_config():
    return {
        "vector_store": {
            "provider": "chroma",
            "config": {"collection_name": CHROMA_COLLECTION, "path": DB_PATH},
        },
        "llm": {"provider": "ollama", "config": {"model": OLLAMA_LLM}},
        "embedder": {"provider": "ollama", "config": {"model": OLLAMA_EMBED}},
    }
