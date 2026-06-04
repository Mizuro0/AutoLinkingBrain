# AutoLinkingBrain

Semantic memory MCP server for [Cursor](https://cursor.com): long-term agent memory via **Mem0**, **Chroma**, and local **Ollama**. Includes Cursor hooks for session bootstrap and autolog, a web **Brain Viewer**, and optional **CodeGraph** companion for code structure.

**Russian documentation:** [docs/README.ru.md](docs/README.ru.md)

## What it does

| Layer | Role |
|-------|------|
| **MCP server** (`brain_server.py` + `autolinkingbrain/mcp_tools/`) | Tools: `storeKnowledge`, `retrieveChain`, `checkProjectHealth`, cross-repo contracts |
| **Cursor hooks** (`.cursor/hooks/`) | Inject context at session start; autolog agent replies and tool use into Mem0 |
| **Brain Viewer** (`viewer_server.py` + `viewer_web/`) | Visual graph of memory channels + Ops metrics dashboard |
| **CodeGraph** (optional, separate binary) | Code structure / symbols — use **before** Brain for navigation |

Cursor starts the MCP server automatically from `~/.cursor/mcp.json`. **`start.bat` / `brain.py`** only bootstrap the environment and launch the viewer — not the MCP process.

## Quick start

```bash
git clone https://github.com/Mizuro0/AutoLinkingBrain.git
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
├── brain_server.py          # MCP bootstrap (~45 LOC; tools in mcp_tools/)
├── viewer_server.py         # HTTP API + static SPA
├── viewer.py                # Deprecated Streamlit viewer (see requirements-legacy.txt)
├── seed_memory.py           # Demo seed data
├── start.bat / start.sh
├── autolinkingbrain/        # Library package
│   ├── mcp_context.py       # Shared MCP runtime (routing, search, health)
│   ├── mcp_tools/           # MCP tool registration (9 tools)
│   ├── mem0_*.py            # Settings, search, privacy, slug, lifecycle, fetch
│   ├── brain_install.py     # MCP/hooks installer (merge_cursor_config)
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
| `VIEWER_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` + `VIEWER_AUTH_TOKEN` for remote) |
| `VIEWER_AUTH_TOKEN` | (unset) | Optional Bearer for `/api/*`; recommended even on localhost in paranoid setups |
| `MEM0_AUTOLOG_BACKEND` | `sqlite` | Hook autolog: `sqlite` (default), `mem0`, or `both` |
| `MEM0_AUTOLOG_USE_OLLAMA` | `0` | `1` = Ollama distill in afterAgentResponse (slow); default heuristic only |
| `MEM0_FETCH_TOP_K` | `500` | Per-channel cap for viewer/API; response includes `truncated` when hit |
| `MEM0_TELEMETRY` | `false` | Set by installer in MCP/hooks env |
| `MCP_HYBRID_SEARCH` | `1` | BM25 + vector RRF in `retrieveChain` |
| `MEM0_MCP_INFER` | `0` | `storeKnowledge` LLM extraction via Ollama (`1` = slow, risks MCP timeout) |
| `MEM0_METRICS` | `1` | Write `.cursor/brain_events.jsonl` |

Full list: [docs/README.ru.md](docs/README.ru.md#переменные-окружения).

## MCP tools (summary)

- **`checkProjectHealth`** / **`sessionContextPack`** — onboarding, indexing state, incoming deps
- **`storeKnowledge`** / **`retrieveChain`** — curated facts and hybrid search across channels
- **`registerDependency`** — cross-repo contract edges in `global_topology`
- **`markIndexingComplete`** — `FINAL_INDEXING_MARK` for reindex protocol
- **`listStaleMemories`** — lifecycle review

Agent protocol: [docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md)

### Cursor skill & project rules

`python brain.py install` / `sync-agent` copy agent assets from `config/cursor/`:

| Template | Target | Cursor UI |
|----------|--------|-----------|
| `config/cursor/skills/*/SKILL.md` | `~/.cursor/skills/<id>/` | Agent Skills |
| `config/cursor/rules/*.mdc` | **`<workspace>/.cursor/rules/`** | Project Rules |

Skills: `autolinking-brain-mcp`, `mcp-triumvirate`, `architecture-by-feature`.  
Rules (always): `autolinking-brain.mdc`, `mem0-auto-write.mdc`. On demand: `triumvirate.mdc`, `architecture-curator.mdc`.

MCP profiles (repo default **`standard`** for forks): `minimal` | `standard` (+ QwenReviewer) | `full` (+ ArchitectureCurator).  
`~/.cursor/rules/` is **not** read by Cursor — rules live in each opened repo.

**Your machine only** — gitignored `config/local/install.yaml` (copy from [config/local/install.yaml.example](config/local/install.yaml.example)):

```yaml
profile: full
sync_mcp_on_agent_sync: true
```

Then `python brain.py mcp install` or `python brain.py sync-agent` applies **full** without changing the public default. See [config/local/README.md](config/local/README.md).

Disable sync: `MEM0_SKIP_CURSOR_AGENT_SYNC=1`. Details: [config/cursor/README.md](config/cursor/README.md).

```powershell
# One-off override (no local yaml):
python brain.py mcp install --profile full

python brain.py sync-agent --force-copy
```

All discovered repos (slow): `python brain.py sync-agent --all-repos`.

## Brain Viewer

- **Memory tab** — force-directed graph by channel (`project_*`, `global_skills`, `global_topology`)
- **Ops tab** — hook/MCP activity, ROI heuristics (`GET /api/metrics`)
- API: `GET /api/memories`, `DELETE /api/memory/{id}`, `GET /api/health`
- Remote access: set `VIEWER_AUTH_TOKEN` when binding `VIEWER_HOST=0.0.0.0` (see [viewer_web/README.md](viewer_web/README.md))
- Localhost: default bind is `127.0.0.1` without auth; set `VIEWER_AUTH_TOKEN` if you want Bearer on loopback too
- Migrate hook noise out of Chroma: `python brain.py migrate-autolog --dry-run` (uses `.venv`; or `.venv\\Scripts\\python.exe scripts/migrate_autolog_to_sqlite.py`)

Restart viewer after updates: `python brain.py start`

### Legacy Streamlit (`viewer.py`)

**Deprecated** — kept for compatibility only. New features go to Brain Viewer only.

```bash
pip install -r requirements-legacy.txt
streamlit run viewer.py
```

Prefer `python brain.py start`. Scripts `start_viewer.ps1` and autostart now launch Brain Viewer.

## Optional scripts

| Script | Purpose |
|--------|---------|
| `scripts/sync_cross_links_to_mem0.py` | Push `memory_cross_links.json` into Mem0 metadata |
| `scripts/suggest_cross_project_links.py` | Ollama-suggested cross-project edges |
| `scripts/migrate_project_memories.py` | Split aggregated project channels |

## Publishing / fork checklist

1. Copy `config/examples/mcp.json.example` paths to your clone location
2. Optional: `config/local/install.yaml` from `install.yaml.example` (gitignored — your MCP profile)
3. Run `python brain.py install`
4. Do **not** commit `chroma_data/`, `.cursor/*.log`, `config/local/install.yaml`, or personal `memory_cross_links.json` (see `.gitignore`)
5. Optional: set `CODEGRAPH_WORKSPACE` or edit `codegraph_repos.txt` for monorepos

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
# or reproducible: pip install -r requirements-lock.txt
python -m pytest tests/ -q
```

CI runs the same suite on push/PR to `main` (`.github/workflows/ci.yml`).

Documentation targets: [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) (≥80% layer READMEs, 100% package module docstrings).
