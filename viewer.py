import streamlit as st
import chromadb
import sys
from pathlib import Path
from chromadb.config import Settings
from mem0 import Memory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0
from autolinkingbrain.mem0_settings import (
    CHROMA_COLLECTION,
    OLLAMA_EMBED,
    OLLAMA_LLM,
    chroma_path_resolved,
    mem0_vector_config,
)

config = mem0_vector_config()
st.set_page_config(page_title="Мозг Cursor", page_icon="🧠")

# Подключаемся к базе (кэшируем, чтобы не переподключаться при каждом клике)
@st.cache_resource
def get_memory():
    return Memory.from_config(config_dict=config)


mem0_db = get_memory()


@st.cache_data(show_spinner=False)
def discover_project_slugs(_refresh: int, resolved_chroma: str, collection_name: str) -> tuple[str, ...]:
    """
    Уникальные имена проектов из метаданных Chroma (user_id вида project_<slug>).
    _refresh — ключ сброса кэша (кнопка «Обновить список»).
    """
    del _refresh  # только для инвалидации кэша Streamlit
    try:
        client = chromadb.PersistentClient(
            path=resolved_chroma,
            settings=Settings(anonymized_telemetry=False),
        )
        col = client.get_collection(collection_name)
    except Exception:
        return ()

    prefix = "project_"
    seen: set[str] = set()
    offset = 0
    batch_size = 2000
    while True:
        batch = col.get(include=["metadatas"], limit=batch_size, offset=offset)
        metas = batch.get("metadatas") or []
        if not metas:
            break
        for meta in metas:
            if not meta:
                continue
            uid = meta.get("user_id")
            if isinstance(uid, str) and uid.startswith(prefix):
                seen.add(uid[len(prefix):])
        if len(metas) < batch_size:
            break
        offset += batch_size

    return tuple(sorted(seen))


_MANUAL_PROJECT = "— Ввести вручную —"

st.title("🧠 База знаний Cursor")
st.info(
    "**Как смотреть проект `backend`:** в режиме «Конкретный проект» выберите или введите slug **`backend`** "
    "(канал в Mem0 — `project_backend`, это **имя корневой папки** workspace в Cursor). "
    "Нажмите **«Загрузить память»** — список сам не обновляется. "
    "После ответа агента смотрите **`<repo>/.cursor/mem0_autolog_last.txt`** — там последний статус хука (Cursor не всегда передаёт `env` из hooks.json). "
    "Подробный лог: тот же каталог **`mem0_autolog_hook.log`** или файл-маркер **`mem0_autolog_debug.on`** в `.cursor`."
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

    slugs = list(
        discover_project_slugs(
            st.session_state["_project_slug_refresh"],
            str(chroma_path_resolved()),
            CHROMA_COLLECTION,
        )
    )

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

# Смена канала — сбрасываем кэш списка (иначе покажутся чужие факты до перезагрузки)
if st.session_state.get("_viewer_user_id") != user_id:
    st.session_state["_viewer_user_id"] = user_id
    st.session_state["_viewer_memories"] = None

if st.button("Загрузить память"):
    with st.spinner("Достаем воспоминания..."):
        raw_response = mem0_db.get_all(filters={"user_id": user_id}, top_k=500)
        log_mem0(
            "read",
            "viewer.get_all",
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
                    log_mem0("write", "viewer.delete", user_id=user_id, memory_id=mid)
                except Exception as exc:
                    st.error(f"Не удалось удалить: {exc}")
                else:
                    raw_response = mem0_db.get_all(filters={"user_id": user_id}, top_k=500)
                    log_mem0(
                        "read",
                        "viewer.get_all",
                        user_id=user_id,
                        top_k=500,
                        rows=count_get_all_rows(raw_response),
                        after="delete",
                    )
                    st.session_state["_viewer_memories"] = (
                        raw_response.get("results", []) if isinstance(raw_response, dict) else raw_response
                    )
                    st.rerun()
