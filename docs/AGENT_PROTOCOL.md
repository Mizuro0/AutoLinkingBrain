# Agent Protocol (host-neutral)

Canonical workflow for any agent host (Cursor, VS Code, CLI, CI).

## 1. Graph before files

For repo overview, stack, architecture, onboarding:

1. Call **`checkProjectHealth`** with `{}` **before** grep/read/search.
2. Summarize `HEALTH STATUS`, `INDEXING COVERAGE`, **`ANALYSIS STATUS`**, `INCOMING DEPENDENCIES`.
3. If `ANALYSIS STATUS` is `required_full` or `required_incremental` and `AUTO_RUN: yes` → call **`runProjectAnalysis`** without asking the user.
4. Then **`sessionContextPack`** / **`retrieveChain`**, then local files.

## 2. MCP stack

| Server | Role | Install profile |
|--------|------|-----------------|
| **AutoLinkingBrain** | Memory, contracts, indexing, analysis | `minimal`+ |
| **CodeGraph** | Symbols, trace, impact (`.codegraph/`) | separate binary |
| **QwenReviewer** | Local Ollama diff review | `standard`+ |
| **ArchitectureCurator** | `docs/ARCHITECTURE.generated.md`, per-feature sections | `full` |

**Repo default** for new clones: MCP profile `standard`. **Your machine:** `config/local/install.yaml` (gitignored, see `config/local/README.md`):

```yaml
profile: full
sync_mcp_on_agent_sync: true
```

```powershell
python brain.py mcp install
python brain.py sync-agent --force-copy
```

One-off override: `python brain.py mcp install --profile full`

**Feature architecture loop (Ollama):** `planArchitectureRun` → per module: Brain + CodeGraph → `runArchitectModule` → `getArchitectHandoff` → read `docs/architecture/modules/<slug>.md` → `recordAgentArchitectureReview` → `storeKnowledge`. Protocol: `docs/ARCHITECTURE_AGENT_PROTOCOL.md`. Skill: `architecture-by-feature`.

## 3. Writes (automated — not optional)

**Chat and hooks do not replace MCP writes.** Hooks produce autolog; structured memory requires explicit tools.

Every non-trivial session:

1. Start: `checkProjectHealth` or `sessionContextPack`
2. During: **`storeKnowledge`** after each architecture decision, bugfix, or API change (English, include file path)
3. End: if nothing stored yet, one summary `storeKnowledge`

English only via MCP tools:

- `storeKnowledge` — facts (`tech`, `scenario`, optional `code_role`)
- `registerDependency` — cross-repo links
- `markIndexingComplete` — only this tool counts as indexed

### storeKnowledge concurrency (MCP stability)

The Brain MCP server is a **single STDIO process** sharing one Chroma collection. Each `storeKnowledge` runs **Ollama embed + Chroma insert** (blocking).

| Do | Don't |
|----|-------|
| One `storeKnowledge`, wait for OK | 2–3 `storeKnowledge` in parallel in one agent turn |
| `scope: project` for task-local facts | `scope: both` unless the fact belongs in `global_skills` too |
| Short body; one fact per call | Batch many facts in one turn without waiting |

Writes go **directly to Chroma** (no server-side serialization) — one `storeKnowledge` at a time, wait for OK before the next.

**Do not batch several storeKnowledge in one agent turn** — Cursor may close MCP STDIO on client timeout while Brain is still writing (`Connection closed` / `transport_closed`). One call → wait for tool result → next call.

**Never force-kill `brain_server` during a write** (`Inserting 1 vectors`): it can corrupt the ChromaDB HNSW vector index, after which every insert crashes the process with a native `access violation` (looks like `Connection closed`). The SQLite store stays intact (reads keep working via `MEM0_FETCH_SQLITE=1`); recover the index losslessly with `python scripts/_chroma_recover.py extract` then `rebuild`. ChromaDB is not safe for concurrent writes from multiple processes — avoid heavy parallel writes from many Cursor windows.

**Diagnostics:** full debug log `.cursor\mcp_full.log`. Tail: `Get-Content D:\mcp_server\.cursor\mcp_full.log -Wait -Tail 30`. Inspect the vector store: `python scripts/_chroma_inspect.py`.

Delivered **globally** (no per-project `.cursor/rules/` required):

- MCP server `instructions` on every AutoLinkingBrain connection
- `~/.cursor/skills/` + `~/.cursor/rules/` via `python brain.py onboard|sync-agent`
- sessionStart hook injects alwaysApply rules (`MEM0_SESSION_PROTOCOL=1`)

Legacy per-repo rules: `MEM0_SYNC_PROJECT_RULES=1` only. Refresh: `python brain.py sync-agent --force-copy`.

## 4. Knowledge GC

Before mass cleanup:

1. `auditKnowledge` (dry-run) → note `CONFIRM_TOKEN`
2. `purgeMemories` with token (`dry_run=true` first)

CLI: `python brain.py gc audit|purge|dedupe-exact`

## 5. MCP server ids (Cursor)

| Server | Global id |
|--------|-----------|
| AutoLinkingBrain | `user-AutoLinkingBrain` |
| CodeGraph | `user-codegraph` |
| ArchitectureCurator | `user-ArchitectureCurator` |
| QwenReviewer | `user-QwenReviewer` |

Project-scoped `.cursor/mcp.json` uses `project-…-<ServerName>` prefixes.

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
