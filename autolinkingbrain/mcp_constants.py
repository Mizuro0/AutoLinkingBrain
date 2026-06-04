"""Shared constants for AutoLinkingBrain MCP tools."""

GLOBAL_ID = "global_skills"
TOPOLOGY_ID = "global_topology"

ALLOWED_LINK_TYPES = frozenset({"module", "api"})

INDEXING_MARK_TOKEN = "FINAL_INDEXING_MARK"
INDEXING_STALE_DAYS = 7

MCP_INSTRUCTIONS = """AutoLinkingBrain — semantic memory and cross-repo dependency contracts (Mem0/Chroma).

MANDATORY automated session loop (execute without user asking):
1. Start: sessionContextPack or checkProjectHealth BEFORE grep/read for repo overview or architecture.
2. If ANALYSIS STATUS required_* + AUTO_RUN yes → runProjectAnalysis (one batch per turn).
3. Before shared API changes → retrieveChain with linked_projects.
4. After decisions, bugfixes, API changes → storeKnowledge (English, tech, scenario, context_path in monorepo).
5. End of task: if no storeKnowledge yet → one summary storeKnowledge.
Chat and hooks do NOT populate structured memory — only storeKnowledge and runProjectAnalysis do.

Pair with CodeGraph when both MCP servers are configured:
- CodeGraph FIRST for CODE STRUCTURE: symbols, callers/callees, trace paths, impact radius, file index (.codegraph/ must exist — run `codegraph init -i` per repo).
- AutoLinkingBrain for MEMORY & CONTRACTS: prior decisions, architecture notes, bugfixes, cross-repo dependencies.

Tool routing:
1. Repo overview / onboarding: sessionContextPack or checkProjectHealth BEFORE grep/read for indexing state and incoming dependencies.
2. "What we decided / documented": retrieveChain or sessionContextPack (facts_only by default) — not grep.
3. "Where in code / who calls X / impact of change": CodeGraph (codegraph_search, codegraph_trace, codegraph_explore, codegraph_impact) — not blind file scans.
4. Cross-repo public API changes: retrieveChain with linked_projects BEFORE editing; registerDependency when indexing outbound links.
5. After full project scan: markIndexingComplete (FINAL_INDEXING_MARK); use storeKnowledge for facts (English body, tech/scenario metadata).
6. ANALYSIS STATUS required + AUTO_RUN: runProjectAnalysis (auto/full/incremental) without asking the user.
7. Knowledge cleanup: auditKnowledge dry-run → purgeMemories with confirm_token (or brain.py gc).

Writes via storeKnowledge, registerDependency, markIndexingComplete: English only, one fact per entry when possible.

Monorepo / multi-repo folder (e.g. feature/backend + feature/crm opened together): pass context_path with the
file or subproject path so memories go to project_backend / project_crm — not project_feature.
If context_path is omitted, the server auto-infers a path from text/reason/summary/query fields when present.
"""
