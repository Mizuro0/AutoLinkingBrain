# AutoLinkingBrain library

Python package shared by the MCP server, Cursor hooks, Brain Viewer, and CLI scripts.

## Modules

| Module | Purpose |
|--------|---------|
| `mem0_settings` | Chroma path, Ollama models, `mem0_vector_config()` |
| `mem0_fetch` | `fetch_all_memories()`, `discover_user_ids()` — viewer + scripts |
| `mem0_project_slug` | Resolve `project_<slug>` from workspace / MCP roots |
| `mem0_hybrid_search` | BM25 + vector RRF for `retrieveChain` |
| `mem0_privacy` / `mem0_provenance` | Secret redaction, write metadata |
| `mem0_lifecycle` | Stale memory thresholds |
| `mem0_kb_log` | Activity log + metrics dual-write |
| `brain_link_store` | `memory_cross_links.json` CRUD |
| `cross_link_mem0_sync` | Sync cross-links into Mem0 |
| `brain_metrics` | `.cursor/brain_events.jsonl` aggregation |
| `brain_install` | Merge `~/.cursor/mcp.json` and hooks |
| `codegraph_init` | Batch CodeGraph indexing |
| `paths` | `REPO_ROOT` constant |
| `mcp_full_log` | MCP stderr/logging capture |

Entry points (`brain_server.py`, `viewer_server.py`, `brain.py`) stay in the repo root for Cursor path configuration.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
