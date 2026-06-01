# Cursor agent assets (skill + global rules)

Canonical templates installed globally by AutoLinkingBrain:

| Source | Installed to | When |
|--------|--------------|------|
| `skills/autolinking-brain-mcp/SKILL.md` | `~/.cursor/skills/autolinking-brain-mcp/SKILL.md` | `brain.py install`, MCP server start |
| `rules/autolinking-brain.mdc` | `~/.cursor/rules/autolinking-brain.mdc` | same |

Implementation: `autolinkingbrain/cursor_agent.py` (`sync_cursor_agent_assets`).

Disable auto-sync: `MEM0_SKIP_CURSOR_AGENT_SYNC=1`.

**Note:** Cursor User Rules in Settings are separate (plain text, UI-only). File-based global rules in `~/.cursor/rules/` are loaded by Agent in many setups; if missing, rely on the skill + MCP instructions.

Agent protocol (full): [docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](../../docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md).
