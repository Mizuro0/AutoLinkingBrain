# Cursor hooks

Installed globally into `%USERPROFILE%\.cursor\hooks.json` by `python brain.py install`.

| Script | Event | Role |
|--------|-------|------|
| `session_mem0_bootstrap.py` | `sessionStart` | Inject recent Mem0 facts into `additional_context` |
| `mem0_autolog_after_response.py` | `afterAgentResponse` | Distill agent reply → Mem0 (`infer=False`) |
| `mem0_autolog_post_tool.py` | `postToolUse` | Log read/edit/search tool use as one-line facts |

All hooks import from `autolinkingbrain` (privacy, slug, settings). They use the same Chroma path as MCP (`MEM0_CHROMA_PATH`).

Disable autolog: `MEM0_AUTOLOG=0` in hook env. Disable session bootstrap: `MEM0_SESSION_BOOTSTRAP=0`.

Template: [config/examples/hooks.json.example](../config/examples/hooks.json.example).
