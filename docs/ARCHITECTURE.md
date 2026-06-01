# Архитектура AutoLinkingBrain

## Обзор

```mermaid
flowchart TB
  subgraph Cursor
    Agent[Cursor Agent]
    Hooks[Cursor Hooks]
    MCPClient[MCP Client]
  end

  subgraph AutoLinkingBrainRepo["AutoLinkingBrain repo"]
    BS[brain_server.py]
    PKG[autolinkingbrain/]
    VW[viewer_server.py]
    UI[viewer_web/]
    HK[.cursor/hooks/]
  end

  subgraph Local
    Ollama[Ollama]
    Chroma[(Chroma / chroma_data)]
    Events[.cursor/brain_events.jsonl]
  end

  subgraph Optional
    CG[CodeGraph MCP]
    CGIdx[.codegraph/ per repo]
  end

  Agent --> MCPClient
  MCPClient --> BS
  BS --> PKG
  BS --> Chroma
  BS --> Ollama

  Hooks --> HK
  HK --> PKG
  HK --> Chroma

  Agent --> Hooks
  VW --> Chroma
  VW --> UI
  PKG --> Events

  Agent --> CG
  CG --> CGIdx
```

## Разделение ответственности

| Компонент | Запуск | Назначение |
|-----------|--------|------------|
| **MCP** (`brain_server.py`) | Cursor через `~/.cursor/mcp.json` | Инструменты памяти для агента |
| **Hooks** (`.cursor/hooks/*.py`) | Cursor через `~/.cursor/hooks.json` | Контекст сессии + автолог без MCP |
| **Viewer** (`brain.py start`) | Пользователь / `start.bat` | Brain Viewer: `viewer_server` + `viewer_web` (граф + Ops) |
| **Legacy UI** (`viewer.py`) | Вручную, Streamlit | **Deprecated** — см. `requirements-legacy.txt` |
| **CodeGraph** | Отдельный MCP + CLI | Структура кода, не память |

**Важно:** `start.bat` не поднимает MCP. Cursor делает это сам при старте IDE.

## Каналы памяти (user_id)

| Канал | Содержимое |
|-------|------------|
| `project_<slug>` | Факты текущего репозитория (slug из MCP roots / workspace) |
| `global_skills` | Переносимые практики между проектами |
| `global_topology` | `[LINK]` зависимости между проектами, `[CROSS_REF_AUTO]` |

Slug резолвится в `autolinkingbrain/mem0_project_slug.py` (monorepo, git root, child repos).

## Пакет `autolinkingbrain/`

| Модуль | Роль |
|--------|------|
| `mem0_settings` | Chroma path, Ollama models, Mem0 config dict |
| `mem0_hybrid_search` | BM25 + vector RRF для `retrieveChain` |
| `mem0_privacy` / `mem0_provenance` | Редакция секретов, метаданные источника |
| `mem0_lifecycle` | Stale detection (viewer badges, `listStaleMemories`) |
| `mem0_kb_log` | Legacy KB log + dual-write в metrics |
| `mem0_fetch` | `fetch_all_memories()` — загрузка всех каналов (viewer + scripts) |
| `brain_metrics` | `brain_events.jsonl`, aggregation, Ops API |
| `brain_link_store` | `memory_cross_links.json` CRUD |
| `cross_link_mem0_sync` | Sync JSON → Mem0 metadata + topology |
| `brain_install` | Merge `mcp.json` / `hooks.json` |
| `codegraph_init` | Batch `codegraph init -i` |
| `paths` | `REPO_ROOT` для путей к данным |

Точки входа (`brain.py`, `brain_server.py`, `viewer_server.py`) остаются в корне репозитория — так проще указать пути в Cursor config.

## Потоки данных

### Запись (write)

1. **MCP `storeKnowledge`** → privacy/provenance → Mem0 → invalidate hybrid cache → metrics
2. **Hook `afterAgentResponse`** → Ollama distill (optional) → Mem0 `infer=False`
3. **Hook `postToolUse`** → one-line tool facts → Mem0

### Чтение (read)

1. **`retrieveChain`** → hybrid search per channel → truncate → MCP response (not logged to agent context from metrics)
2. **`sessionStart` hook** → `get_all` compact list → `additional_context`
3. **Viewer** → `mem0_fetch.fetch_all_memories` + cross_links JSON; UI in `viewer_web/`

## Документация по слоям

| Слой | Файл |
|------|------|
| Корень | [README.md](../README.md) |
| Пакет | [autolinkingbrain/README.md](../autolinkingbrain/README.md) |
| Hooks | [.cursor/hooks/README.md](../.cursor/hooks/README.md) |
| Viewer UI | [viewer_web/README.md](../viewer_web/README.md) |
| Scripts | [scripts/README.md](../scripts/README.md) |
| Contributing | [docs/CONTRIBUTING.md](CONTRIBUTING.md) |

## Файлы состояния (local, в .gitignore)

| Файл | Назначение |
|------|------------|
| `chroma_data/` | Векторная база |
| `memory_cross_links.json` | Рёбра между фактами (viewer + sync) |
| `cross_link_topology_state.json` | Дедуп topology sync |
| `.cursor/brain_events.jsonl` | Ops metrics |
| `.cursor/mem0_*` | Hook debug, dedupe, last run |

## Companion: CodeGraph

- Brain = **память и контракты** между репо
- CodeGraph = **граф кода** (symbols, call graph)
- Routing для агента: CodeGraph first for structure, Brain for decisions/history
- Init: `python brain.py codegraph` или `codegraph init -i` per repo

## Расширение

- Новые MCP tools → `autolinkingbrain/mcp_tools/` + `register()` in `__init__.py`
- Новая логика Mem0 → `autolinkingbrain/` (`mcp_context.py` для shared helpers)
- Новые hook events → `.cursor/hooks/` + update `brain_install._merge_hooks`
- Viewer UI → `viewer_web/` + endpoints in `viewer_server.py` (not legacy `viewer.py`)
