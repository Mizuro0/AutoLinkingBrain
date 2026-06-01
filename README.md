# AutoLinkingBrain

Semantic memory MCP server for [Cursor](https://cursor.com): long-term agent memory via **Mem0**, **Chroma**, and local **Ollama**. Includes Cursor hooks for session bootstrap and autolog, a web **Brain Viewer**, and optional **CodeGraph** companion for code structure.

**Russian documentation:** [docs/README.ru.md](docs/README.ru.md)

## What it does

| Layer | Role |
|-------|------|
| **MCP server** (`brain_server.py`) | Tools: `storeKnowledge`, `retrieveChain`, `checkProjectHealth`, cross-repo contracts |
| **Cursor hooks** (`.cursor/hooks/`) | Inject context at session start; autolog agent replies and tool use into Mem0 |
| **Brain Viewer** (`viewer_server.py` + `viewer_web/`) | Visual graph of memory channels + Ops metrics dashboard |
| **CodeGraph** (optional, separate binary) | Code structure / symbols — use **before** Brain for navigation |

Cursor starts the MCP server automatically from `~/.cursor/mcp.json`. **`start.bat` / `brain.py`** only bootstrap the environment and launch the viewer — not the MCP process.

## Quick start

```bash
git clone https://github.com/YOUR_ORG/autolinkingbrain.git
cd autolinkingbrain
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt

# One-shot install: venv, merge MCP + hooks into ~/.cursor/
python brain.py install --pull-models

# Bootstrap + open viewer (http://127.0.0.1:8501/)
python brain.py start
# or: start.bat   (Windows)   ./start.sh   (Unix)
```

**Requirements:** Python 3.10+, [Ollama](https://ollama.com/) with `llama3.2` and `nomic-embed-text`.

After install, reload Cursor (**Developer: Reload Window**). See [config/examples/](config/examples/) for MCP/hooks templates and [discovery.env.example](config/examples/discovery.env.example) for optional path/slug overrides.

## CLI (`brain.py`)

| Command | Description |
|---------|-------------|
| `start` (default) | Idempotent setup + Brain Viewer |
| `setup` | venv, pip, MCP/hooks merge, Ollama models, CodeGraph init |
| `install` | Full install into `~/.cursor/` |
| `status` | Health: venv, Chroma, Ollama, viewer, CodeGraph discovery |
| `codegraph` | Index discovered repos (`--list`, `--status`, `--force`) |
| `stats` | Offline metrics / ROI from `.cursor/brain_events.jsonl` |

## Project layout

```
autolinkingbrain/
├── brain.py                 # Unified launcher
├── brain_server.py          # MCP entry point
├── viewer_server.py         # HTTP API + static SPA
├── viewer.py                # Legacy Streamlit viewer
├── seed_memory.py           # Demo seed data
├── start.bat / start.sh
├── autolinkingbrain/        # Library package
│   ├── mem0_*.py            # Settings, search, privacy, slug, lifecycle
│   ├── brain_install.py     # MCP/hooks installer
│   ├── brain_metrics.py     # Ops metrics
│   ├── codegraph_init.py    # CodeGraph batch init
│   └── ...
├── .cursor/hooks/           # Cursor hook scripts (installed globally)
├── viewer_web/              # Brain Viewer UI (memory graph + ops)
├── scripts/                 # Optional maintenance scripts
├── config/examples/         # mcp.json, hooks.json templates
└── docs/                    # Architecture, agent protocol (RU)
```

## Environment variables (common)

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEM0_CHROMA_PATH` | `<repo>/chroma_data` | Chroma storage |
| `MEM0_CHROMA_COLLECTION` | `graph_brain` | Collection name |
| `OLLAMA_LLM` / `OLLAMA_EMBED` | `llama3.2` / `nomic-embed-text` | Mem0 models |
| `VIEWER_PORT` | `8501` | Brain Viewer port |
| `MCP_HYBRID_SEARCH` | `1` | BM25 + vector RRF in `retrieveChain` |
| `MEM0_METRICS` | `1` | Write `.cursor/brain_events.jsonl` |

Full list: [docs/README.ru.md](docs/README.ru.md#переменные-окружения).

## MCP tools (summary)

- **`checkProjectHealth`** / **`sessionContextPack`** — onboarding, indexing state, incoming deps
- **`storeKnowledge`** / **`retrieveChain`** — curated facts and hybrid search across channels
- **`registerDependency`** — cross-repo contract edges in `global_topology`
- **`markIndexingComplete`** — `FINAL_INDEXING_MARK` for reindex protocol
- **`listStaleMemories`** — lifecycle review

Agent protocol: [docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md)

## Brain Viewer

- **Memory tab** — force-directed graph by channel (`project_*`, `global_skills`, `global_topology`)
- **Ops tab** — hook/MCP activity, ROI heuristics (`GET /api/metrics`)
- API: `GET /api/memories`, `DELETE /api/memory/{id}`, `GET /api/health`

Restart viewer after updates: `python brain.py start`

## Optional scripts

| Script | Purpose |
|--------|---------|
| `scripts/sync_cross_links_to_mem0.py` | Push `memory_cross_links.json` into Mem0 metadata |
| `scripts/suggest_cross_project_links.py` | Ollama-suggested cross-project edges |
| `scripts/migrate_project_memories.py` | Split aggregated project channels |

## Publishing / fork checklist

1. Copy `config/examples/mcp.json.example` paths to your clone location
2. Run `python brain.py install`
3. Do **not** commit `chroma_data/`, `.cursor/*.log`, or personal `memory_cross_links.json` (see `.gitignore`)
4. Optional: set `CODEGRAPH_WORKSPACE` or edit `codegraph_repos.txt` for monorepos

## License

MIT — see [LICENSE](LICENSE).
