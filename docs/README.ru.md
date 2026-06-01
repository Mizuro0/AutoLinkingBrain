# AutoLinkingBrain — подробная документация (RU)

Краткий обзор на английском: [../README.md](../README.md)  
Архитектура: [ARCHITECTURE.md](ARCHITECTURE.md)  
Протокол агента: [AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md)

## Требования

- Python 3.10+
- [Ollama](https://ollama.com/) с моделями `llama3.2`, `nomic-embed-text`
- [Cursor](https://cursor.com/) с поддержкой MCP и hooks

## Установка

```powershell
cd <путь-к-клону>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python brain.py install --pull-models
```

Или PowerShell-обёртка: `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1`  
(`install.ps1` делегирует merge MCP/hooks в `brain_install.merge_cursor_config` — тот же результат, что `python brain.py install`.)

Шаблоны конфигов: [config/examples/](../config/examples/)

## Что запускает что

| Действие | Кто запускает |
|----------|----------------|
| MCP AutoLinkingBrain | Cursor (`~/.cursor/mcp.json`) |
| Hooks (sessionStart, autolog) | Cursor (`~/.cursor/hooks.json`) |
| Brain Viewer | `start.bat`, `python brain.py start` |
| CodeGraph MCP | Cursor (если добавлен в mcp.json) |

`start.bat` **не** поднимает MCP — только `setup` + viewer на порту 8501.

## Skill и project rules (Cursor Agent)

| Шаблон | Куда | UI Cursor |
|--------|------|-----------|
| `config/cursor/skills/.../SKILL.md` | `~/.cursor/skills/autolinking-brain-mcp/` | Skills |
| `config/cursor/rules/autolinking-brain.mdc` | **`<workspace>/.cursor/rules/`** | **Settings → Rules → Project Rules** |

MCP с `"cwd": "${workspaceFolder}"` копирует rule в **каждый открытый проект** при старте сервера.  
Папка `~/.cursor/rules/` **не** отображается в Settings.

Отключить: `MEM0_SKIP_CURSOR_AGENT_SYNC=1`. Подробнее: [config/cursor/README.md](../config/cursor/README.md).

Полный протокол агента: [AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md).

## Переменные окружения

| Переменная | Назначение | По умолчанию |
|------------|------------|--------------|
| `MEM0_CHROMA_PATH` | Каталог Chroma | `<repo>/chroma_data` |
| `MEM0_CHROMA_COLLECTION` | Имя коллекции | `graph_brain` |
| `OLLAMA_LLM` / `OLLAMA_EMBED` | Модели Mem0 | `llama3.2` / `nomic-embed-text` |
| `MEM0_KB_LOG` | Лог чтений/записей | `1` |
| `MEM0_USE_MCP_ROOTS` | Slug из MCP roots/list | `1` |
| `MCP_HYBRID_SEARCH` | BM25+vector в retrieveChain | `1` |
| `MEM0_STALE_DAYS` | Порог «устарело» в viewer | `90` |
| `VIEWER_PORT` | Порт viewer | `8501` |
| `VIEWER_HOST` | Bind viewer | `127.0.0.1` |
| `VIEWER_AUTH_TOKEN` | Bearer для `/api/*` при remote bind | не задан |
| `MEM0_TELEMETRY` | Телеметрия Mem0/Chroma | `false` (installer) |
| `CODEGRAPH_WORKSPACE` | Корень monorepo для discovery | авто |
| `CODEGRAPH_EXCLUDE_NAMES` | Имена папок — пропуск | не задано |
| `CODEGRAPH_EXCLUDE_PATHS` | Сегменты пути — пропуск | не задано |
| `CODEGRAPH_CONTAINER_NAMES` | Имена «контейнеров» для deep-scan соседей | структура (2+ child repo) |
| `CODEGRAPH_DEPRIORITIZE_PATHS` | Сегменты пути — ниже приоритет при dedupe | не задано |
| `CODEGRAPH_PREFER_PATHS` | Сегменты пути — выше приоритет при dedupe | не задано |
| `MEM0_SUSPICIOUS_SLUGS` | Предупреждение если slug «подозрительный» | не задано |

Полный список хуков: см. раздел «Автозапись» в исторической версии README или env в [hooks.json.example](../config/examples/hooks.json.example).

## MCP (Cursor)

Пример `%USERPROFILE%\.cursor\mcp.json` — см. [mcp.json.example](../config/examples/mcp.json.example).  
`cwd`: `${workspaceFolder}` — fallback для slug, если roots/list недоступен.

## Хуки Cursor

Три скрипта в `.cursor/hooks/`:

- **sessionStart** — `session_mem0_bootstrap.py`: краткий контекст из Mem0
- **afterAgentResponse** — дистилляция ответа через Ollama → Mem0
- **postToolUse** — компактный лог read/edit/search

Устанавливаются командой `python brain.py install` в глобальный `~/.cursor/hooks.json`.

Отладка: `.cursor/mem0_autolog_last.txt`, `MEM0_AUTOLOG_DEBUG=1`.

## Brain Viewer

```powershell
python brain.py start
# или
.\start.bat
```

- **Память** — граф фактов по каналам
- **Ops** — метрики hooks/MCP, ROI (`/api/metrics`)
- Клавиша `O` — вкладка Ops

После обновления кода **перезапустите viewer**.

### Legacy Streamlit (устарело)

`viewer.py` + Streamlit **не развиваются**. Установка: `pip install -r requirements-legacy.txt`, запуск: `streamlit run viewer.py`.  
Скрипты `start_viewer.ps1` и автозагрузка теперь вызывают Brain Viewer.

## CodeGraph

```powershell
python brain.py codegraph --list
python brain.py codegraph
```

Список репо: `codegraph_repos.txt` или auto-discovery. CodeGraph — отдельный MCP для **структуры кода**, Brain — для **памяти**.

## Метрики

```powershell
python brain.py stats
python brain.py stats --days 30 --json
```

События: `.cursor/brain_events.jsonl` (не попадают в контекст агента).

## Межпроектные связи

1. Редактируйте или генерируйте `memory_cross_links.json` (шаблон: [memory_cross_links.example.json](../config/examples/memory_cross_links.example.json))
2. Синхронизация в Mem0: `python scripts/sync_cross_links_to_mem0.py --apply`
3. Предложения от Ollama: `python scripts/suggest_cross_project_links.py --dry-run`

## Заливка тестовых данных

```powershell
.\.venv\Scripts\python.exe seed_memory.py
```

## Структура репозитория

См. [ARCHITECTURE.md](ARCHITECTURE.md).

## Публикация на GitHub

Не коммитьте: `chroma_data/`, логи `.cursor/`, `memory_cross_links.json`, `cross_link_topology_state.json` — см. `.gitignore`.

После клона на новой машине: `python brain.py install` и замените пути в примерах на свой каталог.
