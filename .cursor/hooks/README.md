# Cursor hooks

Installed globally into `%USERPROFILE%\.cursor\hooks.json` by `python brain.py install`.

| Script | Event | Role |
|--------|-------|------|
| `session_mem0_bootstrap.py` | `sessionStart` | Inject recent Mem0 facts into `additional_context` |
| `mem0_autolog_after_response.py` | `afterAgentResponse` | Session archive → `.cursor/autolog.db` (default); optional Mem0 |
| `mem0_autolog_post_tool.py` | `postToolUse` | Tool-use lines → autolog SQLite (`MEM0_TOOLLOG=0` after install) |

Hooks import from `autolinkingbrain` (privacy, slug, autolog_store). Curated memory is **`storeKnowledge`**, not autolog.

Disable autolog: `MEM0_AUTOLOG=0`. Ollama distill: `MEM0_AUTOLOG_USE_OLLAMA=1` (default **off**). Disable session bootstrap: `MEM0_SESSION_BOOTSTRAP=0`.

Template: [config/examples/hooks.json.example](../config/examples/hooks.json.example).
