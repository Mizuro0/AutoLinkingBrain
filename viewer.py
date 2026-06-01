"""
DEPRECATED — legacy Streamlit UI for Mem0.

Use the Brain Viewer instead (graph + Ops dashboard):

  python brain.py start
  http://127.0.0.1:8501/

This module remains for backward compatibility. Install optional deps:

  pip install -r requirements-legacy.txt
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.warn(
    "viewer.py (Streamlit) is deprecated; use 'python brain.py start' (viewer_server + viewer_web).",
    DeprecationWarning,
    stacklevel=1,
)

try:
    import streamlit as st
except ImportError as exc:
    raise SystemExit(
        "Legacy Streamlit viewer requires: pip install -r requirements-legacy.txt\n"
        "Recommended: python brain.py start  (Brain Viewer, no Streamlit)"
    ) from exc

from mem0 import Memory

from autolinkingbrain.mem0_fetch import discover_user_ids
from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0
from autolinkingbrain.mem0_settings import (
    CHROMA_COLLECTION,
    OLLAMA_EMBED,
    OLLAMA_LLM,
    chroma_path_resolved,
    mem0_vector_config,
)

config = mem0_vector_config()
st.set_page_config(page_title="Мозг Cursor (legacy)", page_icon="🧠")

st.warning(
    "**Deprecated.** Use **Brain Viewer**: `python brain.py start` → http://127.0.0.1:8501/ "
    "(interactive graph + Ops). This Streamlit page is kept for compatibility only."
)


@st.cache_resource
def get_memory():
    return Memory.from_config(config_dict=config)


mem0_db = get_memory()


@st.cache_data(show_spinner=False)
def discover_project_slugs(_refresh: int) -> tuple[str, ...]:
    """Project slugs from Chroma user_id channels (project_*)."""
    del _refresh
    return tuple(
        sorted(uid[len("project_") :] for uid in discover_user_ids() if uid.startswith("project_"))
    )


_MANUAL_PROJECT = "— Ввести вручную —"

st.title("🧠 База знаний Cursor (legacy)")
st.info(
    "**Как смотреть проект `backend`:** в режиме «Конкретный проект» выберите или введите slug **`backend`** "
    "(канал в Mem0 — `project_backend`, это **имя корневой папки** workspace в Cursor). "
    "Нажмите **«Загрузить память»** — список сам не обновляется. "
    "После ответа агента смотрите **`<repo>/.cursor/mem0_autolog_last.txt`** — там последний статус хука."
)

with st.sidebar:
    st.subheader("Хранилище")
    st.text(f"Chroma:\n{chroma_path_resolved()}")
    st.caption(f"Коллекция: `{CHROMA_COLLECTION}`")
    st.caption(f"Ollama: `{OLLAMA_LLM}` / `{OLLAMA_EMBED}`")

scope = st.radio(
    "Какой канал памяти смотрим?",
    [
        "Глобальный опыт (global_skills)",
        "Топология зависимостей (global_topology)",
        "Конкретный проект",
    ],
)

user_id = "global_skills"
if scope == "Топология зависимостей (global_topology)":
    user_id = "global_topology"
elif scope == "Конкретный проект":
    if "_project_slug_refresh" not in st.session_state:
        st.session_state["_project_slug_refresh"] = 0

    head, tail = st.columns([3, 1])
    with head:
        st.caption("Список строится по `user_id` в Chroma (все записи с префиксом `project_`).")
    with tail:
        if st.button("Обновить список", key="refresh_project_slugs"):
            st.session_state["_project_slug_refresh"] += 1

    slugs = list(discover_project_slugs(st.session_state["_project_slug_refresh"]))

    project_name = ""
    if slugs:
        choice = st.selectbox(
            "Проект",
            options=slugs + [_MANUAL_PROJECT],
            help="Имена из базы. «Ввести вручную» — если проекта ещё нет в списке.",
        )
        if choice == _MANUAL_PROJECT:
            project_name = st.text_input("Имя папки проекта (как в `project_<имя>`):", "")
        else:
            project_name = choice
    else:
        st.info("В коллекции пока нет записей с `user_id` вида `project_*`. Можно ввести имя вручную.")
        project_name = st.text_input("Имя папки проекта (например, autolinkingbrain):", "")

    if project_name.strip():
        user_id = f"project_{project_name.strip()}"
    else:
        st.warning("Выберите проект из списка или введите имя вручную.")
        st.stop()

st.write(f"**Текущий ID поиска:** `{user_id}`")
st.markdown("---")

if st.session_state.get("_viewer_user_id") != user_id:
    st.session_state["_viewer_user_id"] = user_id
    st.session_state["_viewer_memories"] = None

if st.button("Загрузить память"):
    with st.spinner("Достаем воспоминания..."):
        raw_response = mem0_db.get_all(filters={"user_id": user_id}, top_k=500)
        log_mem0(
            "read",
            "viewer.legacy.get_all",
            user_id=user_id,
            top_k=500,
            rows=count_get_all_rows(raw_response),
        )
        st.session_state["_viewer_memories"] = (
            raw_response.get("results", []) if isinstance(raw_response, dict) else raw_response
        )

memories = st.session_state.get("_viewer_memories")

if memories is None:
    st.caption("Нажмите **Загрузить память**, чтобы подтянуть записи из Mem0.")
elif not memories:
    st.info("В этом канале пока пусто.")
else:
    st.success(f"Найдено фактов: {len(memories)}")

    for mem in memories:
        preview = (mem.get("memory") or "")[:50]
        mid = str(mem.get("id", ""))
        with st.expander(f"📌 {preview}..."):
            st.write("**Полный текст:**")
            st.info(mem.get("memory", ""))
            st.write("**ID в базе:**", mid)

            if st.button("🗑 Удалить факт", key=f"del_{user_id}_{mid}"):
                try:
                    mem0_db.delete(mid)
                    log_mem0("write", "viewer.legacy.delete", user_id=user_id, memory_id=mid)
                except Exception as exc:
                    st.error(f"Не удалось удалить: {exc}")
                else:
                    raw_response = mem0_db.get_all(filters={"user_id": user_id}, top_k=500)
                    log_mem0(
                        "read",
                        "viewer.legacy.get_all",
                        user_id=user_id,
                        top_k=500,
                        rows=count_get_all_rows(raw_response),
                        after="delete",
                    )
                    st.session_state["_viewer_memories"] = (
                        raw_response.get("results", []) if isinstance(raw_response, dict) else raw_response
                    )
                    st.rerun()
