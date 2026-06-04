---
name: autolinking-brain-mcp
description: >-
  AutoLinkingBrain Mem0 MCP — mandatory automated workflow for every coding session:
  sessionContextPack first (brain before grep), syncProjectIndex when AUTO_RUN,
  retrieveChain before contract changes, storeKnowledge after every significant decision.
  Compose architecture: skill architecture-by-feature (you analyze; Ollama per module).
  Use always when AutoLinkingBrain MCP is configured, or for Mem0, indexing, architecture,
  cross-repo contracts, sessionContextPack, retrieveChain, storeKnowledge,
  markIndexingComplete, gc, or project overview.
---

# AutoLinkingBrain (Mem0 MCP) — brain before grep

Installed to `~/.cursor/skills/autolinking-brain-mcp/` by `brain.py install|sync-agent`, sessionStart hook, or first MCP tool (workspace roots). **Not** on every MCP server start.

## Automated session loop (MANDATORY)

```
Task start
  → sessionContextPack { recall_query: "<task-specific keywords>" }
  → user asks refresh/reindex → syncProjectIndex or syncAllProjects (NOT loop runProjectAnalysis)

Before contract/API changes
  → retrieveChain { query, linked_projects, facts_only: true }

While implementing
  → CodeGraph for symbols/trace/impact (not grep-first)

After each significant decision / bugfix / API change
  → storeKnowledge { text EN, tech, scenario, context_path?, scope }

Reindex required
  → registerDependency → storeKnowledge → markIndexingComplete

Task end (if no storeKnowledge yet)
  → storeKnowledge summary fact with file paths
```

**Mem0 is not filled by chat or markdown docs alone.** Hooks = autolog. Index state = **`syncProjectIndex`** / `brain.py analyze sync`. Facts = **`storeKnowledge`**.

## Set-and-forget reindex

| User intent | Tool / CLI |
|-------------|------------|
| Refresh one repo | MCP **`syncProjectIndex`** `{ project_root: "D:/codes/backend", mode: "full" }` |
| Refresh all discovered + extras | MCP **`syncAllProjects`** `{ extra_paths: "D:/codes/backend;D:/codes/altey" }` |
| No MCP / background | `python brain.py analyze sync --paths "D:/codes/backend;D:/codes/altey"` |

Runs in **subprocess** (Windows default) — MCP stays connected. Updates `.brain/project_index.db`; does not spam Mem0 with per-file logs.

## Brain before grep (critical)

| Need | First tool | Fallback |
|------|------------|----------|
| Project context, health, recall | `sessionContextPack` | — |
| Prior decisions / architecture | `retrieveChain` (facts_only) | `syncProjectIndex`; compose arch → `architecture-by-feature` |
| Symbol location, callers, flow | CodeGraph | Read one file |
| Exact string not in graph | grep | — |

If `retrieveChain` returns *No curated facts found* — run analysis or store facts; then grep.

`retrieveChain` default **excludes autolog** (`MCP_RETRIEVE_FACTS_ONLY=1`). Incoming deps in health use **exact** `[LINK] … depends on [slug]`.

## MCP server id

- **Global** `~/.cursor/mcp.json`: **`user-AutoLinkingBrain`**
- **Project** `.cursor/mcp.json`: `project-…-AutoLinkingBrain`

## storeKnowledge

| Field | Rule |
|-------|------|
| text | English, one fact, **include file path** |
| tech | kotlin, python, node, … |
| scenario | architecture, bugfix, api_contract, indexing |
| scope | project / both |
| context_path | monorepo subproject path |

## Companion MCPs

| Intent | MCP | Cursor id (global) |
|--------|-----|-------------------|
| Memory, health, GC, analysis | AutoLinkingBrain | `user-AutoLinkingBrain` |
| Symbols, trace, impact | CodeGraph | `user-codegraph` |
| Feature / module arch doc | ArchitectureCurator | `user-ArchitectureCurator` |
| Diff review (optional) | QwenReviewer | `user-QwenReviewer` |

**Install profiles** (`python brain.py mcp install --scope global --profile …`):

| Profile | Servers |
|---------|---------|
| `minimal` | AutoLinkingBrain |
| `standard` | + QwenReviewer |
| `full` | + ArchitectureCurator |

**Compose architecture** (user: *составить архитектуру*, *спроектировать*): skill **`architecture-by-feature`** — **you** do project analysis & weak spots; Ollama only `runArchitectModule` per module. Not QwenReviewer.

## AUTO_RUN analysis (index state, not arch MD)

When health shows `required_*` + `AUTO_RUN: yes` → **`syncProjectIndex`** / **`syncAllProjects`** (not `runProjectAnalysis` loops). CLI: `python brain.py analyze sync`.

If `ANALYSIS STATUS` is `required_full` and `ENTITIES: 0` — sync index before grep.

**Autolog** is archived in `.cursor/autolog.db` (not curated Mem0). Hooks use `MEM0_AUTOLOG_BACKEND=sqlite` by default.

## Token discipline

- Prefer **one** `sessionContextPack` over health + retrieve separately.
- `top_k_per_scope` ≤ 8; narrow `recall_query`.

Full protocol: `docs/AGENT_PROTOCOL.md`, `docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md`.

## Triumvirate (optional composition)

For alignment + TDD + diagnose on top of Brain/CodeGraph, use skill **`mcp-triumvirate`** and repo **`CONTEXT.md`**.

For **architecture by feature**, use skill **`architecture-by-feature`** (requires profile `full`).

Do not install full ECC — it duplicates memory/hooks. Setup: `docs/TRIUMVIRATE.md`.
