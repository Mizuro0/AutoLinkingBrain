---
name: autolinking-brain-mcp
description: >-
  Uses the AutoLinkingBrain Mem0 MCP (knowledge graph) across any workspace:
  checkProjectHealth, reindex protocol, registerDependency, retrieveChain,
  storeKnowledge, markIndexingComplete. Use when the user works with Mem0,
  AutoLinkingBrain, project indexing, incoming dependencies, cross-repo
  contracts, sessionContextPack, or asks for repo overview/stack/architecture
  while this MCP is configured.
---

# AutoLinkingBrain (Mem0 MCP) — any workspace

Installed globally to `~/.cursor/skills/autolinking-brain-mcp/` by `python brain.py install` and refreshed when the MCP server starts.

## MCP server id for `call_mcp_tool`

The `server` argument is **not** always the `mcp.json` key `AutoLinkingBrain`.

- **Global** (`%USERPROFILE%\.cursor\mcp.json`): **`user-AutoLinkingBrain`** (i.e. `user-` + servers key).
- **Project-scoped** (`.cursor/mcp.json`): **`project-<n>-<workspaceFolderBasename>-AutoLinkingBrain`** — if calls fail, read the exact id from Cursor MCP logs/UI.

Prefer **global** MCP with `"cwd": "${workspaceFolder}"` so **`user-AutoLinkingBrain`** stays stable across repos.

## CodeGraph companion (if configured)

MCP id: typically **`user-codegraph`**. Needs `.codegraph/` per repo (`codegraph init -i` or `scripts/init_codegraph_project.ps1`).

| Intent | MCP |
|---|---|
| Health, reindex, incoming deps, stored decisions | **AutoLinkingBrain** |
| Callers, trace, impact, symbol search | **CodeGraph** |

Do not grep/read for structure when CodeGraph tools suffice. After `checkProjectHealth`, use CodeGraph before blind file scans for architecture questions.

## Repo / project questions → graph before files

For overview, stack, architecture, “what is this project”, onboarding, high-level survey of the **opened workspace**:

1. **First tool call:** MCP **`checkProjectHealth`** with `{}` and the correct **`server`** (default **`user-AutoLinkingBrain`**).
2. **Do not** use `read_file`, `list_dir`, `grep`, `glob_file_search`, `codebase_search` (or similar) **until** `checkProjectHealth` returns or errors.
3. Summarize `STATUS`, `REINDEX_PROTOCOL`, **INCOMING DEPENDENCIES** for the user (user language per user rules; default concise).
4. Then optionally **`sessionContextPack`** or **`retrieveChain`**, then local files as needed.

`sessionStart` **additional_context** from Mem0 is **supplementary** — it does **not** replace `checkProjectHealth` for indexing / reindex / incoming links.

If MCP errors or is unavailable: say so in one short sentence, then continue with files **without** claiming health was read.

## Reindex required (`REINDEX_PROTOCOL`)

When health says full indexing is needed:

1. Scan **internal modules** for this stack (Gradle `project(":…")`, Maven `<module>`, npm/pnpm workspaces, Go `replace`, Cargo workspaces, etc.).
2. Scan **outbound APIs** (HTTP clients, OpenAPI/Swagger, gRPC/proto, shared DTO packages).
3. For each finding: **`registerDependency`** with `link_type` `module` or `api` and **English, factual** `reason`.
4. Scan entrypoints and integration surfaces; **`storeKnowledge`** project summary (`scope` `project` or `both`), **English** body, accurate `tech` / `scenario`.
5. **`markIndexingComplete(summary="…")`** with **English** summary (final mark for health).

Treat **incoming** real links as **contracts** — document public surfaces; avoid breaking changes without a migration plan.

## Indexing mark (`FINAL_INDEXING_MARK`)

Only an explicit MCP **`markIndexingComplete`** call counts as indexed (`infer=False` on the server).

Hook autolog or other memories that *mention* `FINAL_INDEXING_MARK` do **not** satisfy **`checkProjectHealth`**. Always finish reindex with the tool, not a chat summary or autolog line.

## Before changing shared contracts

Call **`retrieveChain`** with `linked_projects=["<dependent_slug>"]` (stable repo slug, not paths). If the tool returns nothing, state that and proceed carefully. Do not invent tool output.

## `storeKnowledge` / graph writes

- **`tech`**: concrete stack tokens (Kotlin, Spring, Node, Python, FastAPI, …).
- **`scenario`**: e.g. `architecture`, `bugfix`, `api_contract`, `indexing`.
- **`scope`**: `project` | `global` | `both`.
- **Memory body and factual dependency reasons**: **English** only (clear, searchable).

## Monorepo folder (several repos under one Cursor workspace)

When the opened folder is a **parent** (e.g. `feature/`) containing subprojects (`backend/`, `crm/`, …):

1. Pass **`context_path`** on every write/read tool with the **file or subfolder** you are working on  
   (`backend/src/...`, `crm/api/...`). Memories must land in `project_backend`, `project_crm` — **not** `project_feature`.
2. If you omit `context_path`, the MCP server **auto-infers** a path from `text`, `reason`, `summary`, or `query` when those fields contain file paths.
3. Include at least one **concrete path** in `storeKnowledge.text` when you cannot pass `context_path` explicitly.
4. Tool responses echo the resolved channel: `→ project_<slug> (auto-routed from path in payload: …)`.

Per-subproject override (optional): `<subproject>/.cursor/mem0_project_slug` with one line (`backend`, `crm_server`, …).

## Provenance on writes

New Mem0 rows are prefixed with **`[SOURCE: …]`** (English): e.g. `mcp:storeKnowledge`, `hook:postToolUse tool=Read`, `hook:afterAgentResponse`. Disable with `MEM0_PROVENANCE=0`. Use in viewer/search to see origin.

## CodeGraph index (companion MCP)

Requires `codegraph` on PATH. **Auto-discovery is ON by default** (same layout as Mem0 slug):

- sibling git repos next to `mcp_server` (e.g. `D:\codes\*` when server lives in `D:\codes`)
- child repos under `CODEGRAPH_WORKSPACE` or cwd (`feature/backend`, …)
- depth `CODEGRAPH_SCAN_DEPTH` (default 2)

```bash
python brain.py codegraph list      # see discovered paths
python brain.py codegraph init      # init all discovered
python brain.py codegraph status
```

Monorepo only: `CODEGRAPH_WORKSPACE=D:\feature` or `python brain.py codegraph init --workspace D:\feature`.

Manual extras (optional): `codegraph_repos.txt` or `CODEGRAPH_REPOS` — only if auto-discovery misses a repo.
Disable auto: `CODEGRAPH_AUTO_DISCOVER=0` or `--no-auto`.

## Token discipline

- Prefer **`sessionContextPack`** once for broad context instead of redundant `checkProjectHealth` + `retrieveChain` for the same goal.
- **`retrieveChain`**: narrow `query`, `top_k_per_scope` ≤ 8 unless necessary; `per_memory_chars` ~800–1200.
- Hybrid **BM25 + vector (RRF)** is on by default (`MCP_HYBRID_SEARCH=1`) — good for exact tokens (API names, `FINAL_INDEXING_MARK`, file paths) plus semantic recall.
- Do not dump full MCP payloads in chat unless needed.

## Tool naming

Use the **camelCase** tool names exposed by the server (e.g. `checkProjectHealth`, `storeKnowledge`). If Cursor allowlist blocks tools, align names with the server and user MCP config.

Full protocol: `docs/AUTONOMOUS_KNOWLEDGE_GRAPH_PROTOCOL.md` in the AutoLinkingBrain repo.
