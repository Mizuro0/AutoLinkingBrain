# Agent Protocol (host-neutral)

Canonical workflow for any agent host (Cursor, VS Code, CLI, CI).

## 1. Graph before files

For repo overview, stack, architecture, onboarding:

1. Call **`checkProjectHealth`** with `{}` **before** grep/read/search.
2. Summarize `HEALTH STATUS`, `INDEXING COVERAGE`, **`ANALYSIS STATUS`**, `INCOMING DEPENDENCIES`.
3. If `ANALYSIS STATUS` is `required_full` or `required_incremental` and `AUTO_RUN: yes` → call **`runProjectAnalysis`** without asking the user.
4. Then **`sessionContextPack`** / **`retrieveChain`**, then local files.

## 2. Dual MCP

- **CodeGraph** — code structure, symbols, trace, impact (when `.codegraph/` exists).
- **AutoLinkingBrain** — memory, contracts, indexing, analysis orchestrator.
- **QwenReviewer** (optional) — diff review.
- **ArchitectureCurator** (optional, profile full) — `docs/ARCHITECTURE.generated.md`.

## 3. Writes

English only via MCP tools:

- `storeKnowledge` — facts (`tech`, `scenario`, optional `code_role`)
- `registerDependency` — cross-repo links
- `markIndexingComplete` — only this tool counts as indexed

## 4. Knowledge GC

Before mass cleanup:

1. `auditKnowledge` (dry-run) → note `CONFIRM_TOKEN`
2. `purgeMemories` with token (`dry_run=true` first)

CLI: `python brain.py gc audit|purge|dedupe-exact`

## 5. MCP server ids (Cursor)

| Scope | Typical id |
|-------|------------|
| Global `~/.cursor/mcp.json` | `user-AutoLinkingBrain` |
| Project `.cursor/mcp.json` | `project-…-AutoLinkingBrain` |

## 6. Metrics tiers

| Tier | Where | Who |
|------|-------|-----|
| Local viewer Ops | `.cursor/brain_events.jsonl` | User on device |
| Fleet Hub | Admin VPS `fleet.html` | Admin only (sanitized refs) |

Users never see fleet dashboard; viewer does not proxy hub.

## 7. Setup

```powershell
python brain.py onboard --host cursor --mcp-scope global
python brain.py doctor
```

Config: `~/.config/autolinkingbrain/config.toml` (or `%APPDATA%/autolinkingbrain/config.toml`).

See also: [AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md](AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md), [QUICKSTART.ru.md](QUICKSTART.ru.md).
