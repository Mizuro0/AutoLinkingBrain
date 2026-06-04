# Cursor agent assets (skill + global rules)

Canonical templates installed by AutoLinkingBrain **once per machine** — no per-project setup for forks.

| Source | Installed to | Scope |
|--------|--------------|-------|
| `skills/*/SKILL.md` | `~/.cursor/skills/<id>/SKILL.md` | **Global** — all workspaces |
| `rules/*.mdc` (alwaysApply) | `~/.cursor/rules/*.mdc` | **Global** — all workspaces |
| `rules/*.mdc` (on demand) | same | Agent-requested rules in Settings |

**Protocol delivery (3 layers, no project `.cursor/rules/` required):**

1. **MCP server instructions** — every AutoLinkingBrain tool call (always when MCP configured)
2. **Global skills** — `~/.cursor/skills/autolinking-brain-mcp/`
3. **sessionStart hook** — injects alwaysApply rules text + Mem0 bootstrap (`MEM0_SESSION_PROTOCOL=1` default)

Per-project `.cursor/rules/` is **legacy opt-in** only: `MEM0_SYNC_PROJECT_RULES=1` or `brain.py sync-agent --all-repos` with that env.

## When files are synced

| Event | Global skill | Global rules | Project rules |
|-------|--------------|--------------|---------------|
| `python brain.py install` | yes | yes | only if `MEM0_SYNC_PROJECT_RULES=1` |
| `python brain.py onboard` | yes | yes | same |
| `python brain.py sync-agent` | yes | yes | `--all-repos` + env only |
| Hook `sessionStart` | refresh if stale | refresh if stale | no |
| MCP first tool (roots) | refresh if stale | refresh if stale | no |

Implementation: `autolinkingbrain/cursor_agent.py`. Disable: `MEM0_SKIP_CURSOR_AGENT_SYNC=1`.

Fork workflow: clone → `pip install -r requirements.txt` → `python brain.py onboard` → Reload Cursor. Done.

Agent protocol: [docs/AGENT_PROTOCOL.md](../../docs/AGENT_PROTOCOL.md).
