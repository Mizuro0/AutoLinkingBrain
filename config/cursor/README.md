# Cursor agent assets (skill + project rules)

Canonical templates installed by AutoLinkingBrain:

| Source | Installed to | Visible in Cursor Settings |
|--------|--------------|----------------------------|
| `skills/autolinking-brain-mcp/SKILL.md` | `~/.cursor/skills/autolinking-brain-mcp/SKILL.md` | Skills (agent picks by description) |
| `rules/autolinking-brain.mdc` | **`<workspace>/.cursor/rules/`** | **Rules → Project Rules** (`alwaysApply: true`) |
| `rules/mem0-auto-write.mdc` | **`<workspace>/.cursor/rules/`** | **Rules → Project Rules** (`alwaysApply: true`) |

**Important:** `~/.cursor/rules/` is **not** read by Cursor Settings. Project rules must live in the **opened workspace** at `.cursor/rules/*.mdc`.

## When files are synced

| Event | Skill (global) | Project rules |
|-------|----------------|---------------|
| `python brain.py install` | yes | yes → all auto-discovered repos + repo root |
| `python brain.py sync-agent` | yes | yes → all auto-discovered git repos (manual refresh) |
| `python brain.py setup` | yes | yes → all auto-discovered repos |
| MCP first tool call (MCP roots) | — | yes → each MCP workspace root |
| Hook `sessionStart` | — | yes → `workspace_roots` + `cwd` from hook payload |
| MCP server start (`brain_server.py`) | yes | yes → MCP `cwd` only (one process, first workspace) |

**Why other projects were empty:** Cursor keeps one MCP process alive; `cwd` is set only at first start. Rules now also sync via **sessionStart hook** and **install/setup discovery** (`collect_repo_paths` — same as CodeGraph).

**Important:** Project rules appear in Settings only after `.cursor/rules/*.mdc` exists in that folder. Opening Agent chat in a project triggers `sessionStart`; or run `python brain.py sync-agent` once.

Implementation: `autolinkingbrain/cursor_agent.py`. Disable: `MEM0_SKIP_CURSOR_AGENT_SYNC=1`.

User Rules (Settings text field) are separate and stored inside Cursor — not managed by this installer.

Agent protocol (full): [docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](../../docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md).
