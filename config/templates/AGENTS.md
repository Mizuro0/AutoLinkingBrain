# Agent protocol (host-neutral)

See [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md) for the canonical workflow.

## Automated rules (mandatory when Brain MCP is configured)

1. **Session start** — `checkProjectHealth` (or `sessionContextPack` once) before grep/read for repo questions.
2. **Analysis AUTO_RUN** — `runProjectAnalysis` when health shows `required_*` + `AUTO_RUN: yes` (no user prompt).
3. **Auto-write** — after every significant decision, bugfix, or API change → **`storeKnowledge`** (English, with file path).
4. **Contracts** — `retrieveChain` + `linked_projects` before breaking shared APIs.
5. **Reindex** — `registerDependency` → `storeKnowledge` → `markIndexingComplete` (tool only, not autolog).
6. **Structure** — CodeGraph when `.codegraph/` exists.
7. **Feature architecture** — ArchitectureCurator (profile `full`); skill `architecture-by-feature`.
8. **GC** — `auditKnowledge` before `purgeMemories`.

**Global delivery** — MCP instructions + `~/.cursor/skills/` + `~/.cursor/rules/` + sessionStart hook. Fork: `python brain.py onboard` → Reload Cursor.

Refresh: `python brain.py sync-agent --force-copy`
