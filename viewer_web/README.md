# Brain Viewer UI

Static SPA served by `viewer_server.py` (default `http://127.0.0.1:8501/`).

| File | Role |
|------|------|
| `index.html` | Memory graph — channels, topics, search, stale badges |
| `ops.html` | Ops dashboard — metrics from `/api/metrics` |

## HTTP API (viewer_server)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/memories` | All facts + `cross_links` JSON |
| GET | `/api/metrics?days=7&recent=80` | Hook/MCP activity (Ops tab) |
| GET | `/api/health` | Chroma path, collection name |
| DELETE | `/api/memory/{id}` | Delete one fact |
| DELETE | `/api/scope/{user_id}` | Delete entire channel |
| DELETE | `/api/batch` | Body `{"ids": [...]}` |

Data loading uses `autolinkingbrain.mem0_fetch.fetch_all_memories`.

Legacy table UI: deprecated `viewer.py` (Streamlit) — see [requirements-legacy.txt](../requirements-legacy.txt).
