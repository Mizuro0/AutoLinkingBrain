# Agent protocol (host-neutral)

See [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md) for the canonical workflow.

## Quick rules

1. **Graph before files** — `checkProjectHealth` before grep/read for repo overview.
2. **Memory** — `retrieveChain` / `sessionContextPack` for decisions and contracts.
3. **Code structure** — CodeGraph when `.codegraph/` exists.
4. **Writes** — English only via `storeKnowledge`, `registerDependency`, `markIndexingComplete`.
5. **Analysis** — when `ANALYSIS STATUS: required`, run `runProjectAnalysis` without asking the user (AUTO_RUN).
6. **GC** — `auditKnowledge` dry-run before `purgeMemories`.

Cursor-specific hints: skill `autolinking-brain-mcp`, MCP server id `user-AutoLinkingBrain` (global scope).
