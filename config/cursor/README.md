# Cursor agent assets (skill + project rules)

Canonical templates installed by AutoLinkingBrain:

| Source | Installed to | Visible in Cursor Settings |
|--------|--------------|----------------------------|
| `skills/autolinking-brain-mcp/SKILL.md` | `~/.cursor/skills/autolinking-brain-mcp/SKILL.md` | Skills (agent picks by description) |
| `rules/autolinking-brain.mdc` | **`<workspace>/.cursor/rules/`** | **Rules → Project Rules** |

**Important:** `~/.cursor/rules/` is **not** read by Cursor Settings. Project rules must live in the **opened workspace** at `.cursor/rules/*.mdc`.

## When files are synced

| Event | Skill (global) | Project rules |
|-------|----------------|---------------|
| `python brain.py install` | yes | yes → AutoLinkingBrain repo root |
| MCP server start (`brain_server.py`) | yes | yes → MCP `cwd` (= `${workspaceFolder}`) |
| `python brain.py setup` | yes | yes → repo root |

So every project where Cursor starts AutoLinkingBrain MCP gets the rule file automatically on first MCP connection.

Implementation: `autolinkingbrain/cursor_agent.py`. Disable: `MEM0_SKIP_CURSOR_AGENT_SYNC=1`.

User Rules (Settings text field) are separate and stored inside Cursor — not managed by this installer.

Agent protocol (full): [docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](../../docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md).
