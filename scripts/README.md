# Optional maintenance scripts

| Script | Purpose |
|--------|---------|
| `install.ps1` | Windows installer (venv, MCP, hooks) — prefer `python brain.py install` |
| `start_brain_viewer.ps1` | Start Brain Viewer via `brain.py start` |
| `start_viewer.ps1` | Alias → `start_brain_viewer.ps1` (formerly Streamlit) |
| `sync_cross_links_to_mem0.py` | Push `memory_cross_links.json` into Mem0 |
| `suggest_cross_project_links.py` | Ollama-suggested cross-project edges |
| `migrate_project_memories.py` | Split aggregated `project_*` channels |
| `migrate_project_groups.ps1` | Batch wrapper for migration (requires `-SourceSlugs`) |

Most scripts add the repo root to `sys.path` and import `autolinkingbrain.*` — they do not import `viewer_server` internals.
