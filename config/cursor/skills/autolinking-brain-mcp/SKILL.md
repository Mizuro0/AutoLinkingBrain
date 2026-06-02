---
name: autolinking-brain-mcp
description: >-
  AutoLinkingBrain Mem0 MCP — mandatory automated workflow for every coding session:
  checkProjectHealth first, runProjectAnalysis when AUTO_RUN, retrieveChain before
  contract changes, storeKnowledge after every significant decision. Use always
  when AutoLinkingBrain MCP is configured, or for Mem0, indexing, architecture,
  cross-repo contracts, sessionContextPack, retrieveChain, storeKnowledge,
  markIndexingComplete, gc, or project overview.
---

# AutoLinkingBrain (Mem0 MCP) — automated

Installed to `~/.cursor/skills/autolinking-brain-mcp/` by `brain.py install|onboard|sync-agent` and refreshed on MCP server start.

## Automated session loop (MANDATORY)

Execute without waiting for the user to ask:

```
Task start
  → checkProjectHealth {}  (or sessionContextPack once if recall needed)
  → if ANALYSIS required_* + AUTO_RUN → runProjectAnalysis (one batch)

Before contract/API changes
  → retrieveChain { query, linked_projects }

After each significant decision / bugfix / API change
  → storeKnowledge { text EN, tech, scenario, context_path?, scope }

Reindex required
  → registerDependency → storeKnowledge → markIndexingComplete

Task end (if no storeKnowledge yet)
  → storeKnowledge summary fact
```

**Mem0 is not filled by chat or markdown docs alone.** Hooks = autolog. Structured memory = **`storeKnowledge`**.

## MCP server id

- **Global** `~/.cursor/mcp.json`: **`user-AutoLinkingBrain`**
- **Project** `.cursor/mcp.json`: `project-…-AutoLinkingBrain` (check MCP logs if calls fail)

## Graph before files

For repo overview, stack, architecture, onboarding:

1. **`checkProjectHealth`** before read/grep/glob/codebase_search.
2. Summarize STATUS, REINDEX_PROTOCOL, INDEXING COVERAGE, ANALYSIS STATUS, INCOMING DEPENDENCIES.
3. Then sessionContextPack / retrieveChain, then local files.

sessionStart hook context is supplementary — not a substitute for checkProjectHealth.

## storeKnowledge (auto-write rules)

| Field | Rule |
|-------|------|
| text | English, one fact, include file path when possible |
| tech | kotlin, python, node, … |
| scenario | architecture, bugfix, api_contract, indexing |
| scope | project (local) / both (reusable) |
| context_path | monorepo subproject path → correct project_<slug> |

Parallel calls: max ~3 storeKnowledge at once; retry on Connection closed.

## Reindex (REINDEX_PROTOCOL: required)

1. Scan modules + outbound APIs (Gradle/Maven/npm/…).
2. registerDependency per link (English reason).
3. storeKnowledge summaries (architecture + api_contract).
4. checkProjectHealth → COVERAGE sufficient.
5. markIndexingComplete (only this tool counts; autolog does not).

Coverage env: MEM0_INDEXING_MIN_FACTS=8, REQUIRED_SCENARIOS=architecture,api_contract, STRICT=1.

## Before changing shared contracts

retrieveChain with linked_projects=["dependent_slug"]. If empty, say so and proceed carefully.

## Companion MCPs

| Intent | MCP |
|--------|-----|
| Memory, health, GC, analysis | AutoLinkingBrain |
| Symbols, trace, impact | CodeGraph (`user-codegraph`) |
| Diff review | QwenReviewer |
| ARCHITECTURE.generated.md | ArchitectureCurator (profile full) |

## AUTO_RUN analysis

When health shows ANALYSIS STATUS required_* + AUTO_RUN yes → runProjectAnalysis without asking. CLI fallback: `python brain.py analyze auto`.

## Knowledge GC

auditKnowledge → purgeMemories (dry_run first). CLI: `brain.py gc audit|purge`.

## Token discipline

- sessionContextPack once instead of redundant health + retrieve.
- retrieveChain: top_k_per_scope ≤ 8, narrow query.
- Do not dump full MCP payloads in chat.

## Monorepo routing

Pass context_path on every tool (backend/src/…). Server auto-infers from paths in text if omitted.

Full protocol: `docs/AGENT_PROTOCOL.md`, `docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md`. Onboard: `python brain.py onboard`.
