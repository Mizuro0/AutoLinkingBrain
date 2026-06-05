# Agent protocol (host-neutral)

See [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md) for the canonical workflow.

## Automated rules (mandatory when Brain MCP is configured)

1. **Session start** — `checkProjectHealth` (or `sessionContextPack` once) before grep/read for repo questions.
2. **Analysis AUTO_RUN** — `runProjectAnalysis` when health shows `required_*` + `AUTO_RUN: yes` (no user prompt).
3. **Auto-write** — after every significant decision, bugfix, or API change → **`storeKnowledge`** (English, with file path). Chat/hooks alone do not populate structured memory.
4. **Contracts** — `retrieveChain` + `linked_projects` before breaking shared APIs.
5. **Reindex** — `registerDependency` → `storeKnowledge` → `markIndexingComplete` (tool only, not autolog).
6. **Structure** — CodeGraph when `.codegraph/` exists.
7. **Compose architecture** (user request) — skill `architecture-by-feature` + rule `architecture-curator.mdc`: **host agent** analyzes project/weak spots; Ollama `runArchitectModule` per module; then `storeKnowledge`.
8. **GC** — `auditKnowledge` before `purgeMemories`.

Cursor: skills `autolinking-brain-mcp`, `mcp-triumvirate`, `architecture-by-feature`; rules `autolinking-brain.mdc` + `mem0-auto-write.mdc` (always on), `triumvirate.mdc` + `architecture-curator.mdc` (on demand).

MCP ids (global): `user-AutoLinkingBrain`, `user-codegraph`, `user-ArchitectureCurator` (full), `user-QwenReviewer` (standard).

Refresh: `python brain.py sync-agent --force-copy` (also refreshes MCP when `sync_mcp_on_agent_sync: true` in `config/local/install.yaml`).

MCP on **this machine**: copy `config/local/install.yaml.example` → `config/local/install.yaml` (`profile: full` gitignored). Then `python brain.py mcp install` without flags.

Triumvirate: [docs/TRIUMVIRATE.md](docs/TRIUMVIRATE.md). Domain terms: [CONTEXT.md](CONTEXT.md).

## Agent skills

### Issue tracker

GitHub Issues on `Mizuro0/AutoLinkingBrain` via `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at repo root and `docs/adr/` for ADRs. See `docs/agents/domain.md`.
