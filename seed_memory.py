"""
Однократная (или повторная) заливка тестовых записей в Mem0/Chroma.

Путь к данным Chroma задаётся в mem0_settings (переменная MEM0_CHROMA_PATH или каталог chroma_data в корне репо).

Запуск: .venv\\Scripts\\python.exe seed_memory.py
"""
from __future__ import annotations

import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mem0 import Memory

from autolinkingbrain.mem0_settings import mem0_vector_config

logging.getLogger("chromadb").setLevel(logging.ERROR)

GLOBAL_ID = "global_skills"
TOPOLOGY_ID = "global_topology"
PROJECT_ID = "mcp_server"
PROJECT_USER = f"project_{PROJECT_ID}"
NOW = datetime.now().isoformat()


def main() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mem = Memory.from_config(config_dict=mem0_vector_config())

    seeds: list[tuple[str, str]] = [
        # (user_id, text)
        (
            GLOBAL_ID,
            f"[PYTHON] [CONVENTION] (Updated: {NOW}): Для MCP на stdio нельзя писать в stdout кроме JSON; предупреждения библиотек глушить при инициализации Memory.",
        ),
        (
            GLOBAL_ID,
            f"[MEM0] [ARCHITECTURE] (Updated: {NOW}): Один каталог Chroma (graph_brain) + разные user_id: global_skills, project_*, global_topology.",
        ),
        (
            PROJECT_USER,
            f"[SYSTEM] [INDEXING] (Updated: {NOW}): FINAL_INDEXING_MARK (completed_at={NOW}) seed_memory.py; проект mcp_server: MCP (FastMCP) + Mem0 + Ollama, mem0_settings.py.",
        ),
        (
            PROJECT_USER,
            f"[PYTHON] [SETUP] (Updated: {NOW}): viewer.py и brain_server.py должны использовать mem0_vector_config() чтобы коллекция Chroma совпадала.",
        ),
        (
            TOPOLOGY_ID,
            "[LINK] [demo-booking] depends on [mcp_server] via [API]. Contract: чтение долгосрочной памяти через MCP tools (пример входящей связи для health check).",
        ),
        (
            TOPOLOGY_ID,
            "[LINK] [mcp_server] depends on [ollama] via [API]. Contract: llama3.2 + nomic-embed-text на localhost для add/search.",
        ),
    ]

    for user_id, text in seeds:
        mem.add(text, user_id=user_id)
        print(f"OK user_id={user_id!r} len={len(text)}")

    print("Done. In Streamlit check: global_skills, project_mcp_server, global_topology.")


if __name__ == "__main__":
    main()
