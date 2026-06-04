# Brain Viewer UI

Static SPA served by `viewer_server.py` (default `http://127.0.0.1:8501/`).

| File | Role |
|------|------|
| `index.html` | Memory graph — channels, topics, search, stale badges |
| `autolog.html` | Session autolog — SQLite hook archive (separate from Mem0 facts) |
| `ops.html` | Ops dashboard — metrics from `/api/metrics` |

## HTTP API (viewer_server)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/memories` | All facts + `cross_links` JSON |
| GET | `/api/metrics?days=7&recent=80` | Hook/MCP activity (Ops tab) |
| GET | `/api/health` | Chroma path, collection name |
| GET | `/api/autolog?project=&q=&limit=50` | Hook session archive (`.cursor/autolog.db`) |
| GET | `/api/autolog/projects` | Distinct project slugs in autolog DB |
| DELETE | `/api/memory/{id}` | Delete one fact |
| DELETE | `/api/scope/{user_id}` | Delete entire channel (`?confirm=1` if batch cap hit) |
| DELETE | `/api/batch` | Body `{"ids": [...]}` |

Data loading uses `autolinkingbrain.mem0_fetch.fetch_all_memories`.

## Security

- Default bind: `VIEWER_HOST=127.0.0.1` (local only).
- Remote bind (`0.0.0.0`): set **`VIEWER_AUTH_TOKEN`** — required on all `/api/*` via `Authorization: Bearer <token>` or `X-Viewer-Token`.
- Localhost: without a token, any local process can use the API; set `VIEWER_AUTH_TOKEN` for paranoid loopback setups.
- `GET /api/memories` includes `truncated: true` when a channel reaches `MEM0_FETCH_TOP_K` (default 500).
- By default **`MEM0_FETCH_SQLITE=1`**: reads `chroma.sqlite3` directly (avoids chromadb client crashes on Windows). Set `MEM0_FETCH_SQLITE=0` only if the Python client is stable on your OS.
- Large graphs (>150 facts): Brain Viewer uses **overview mode** — canvas shows channels/topics only; use search or channel filter to expand facts on the graph.
- Static HTML is served without token (SPA); API mutations stay protected when token is set.

Legacy table UI: deprecated `viewer.py` (Streamlit) — see [requirements-legacy.txt](../requirements-legacy.txt).
