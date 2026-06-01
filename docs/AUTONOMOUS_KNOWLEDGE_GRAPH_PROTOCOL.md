# Autonomous Knowledge Graph Protocol

## Scope

- Applies to any repository opened in the workspace (not Kotlin-only).
- Kotlin/JVM hints are **examples**; adapt the same steps to the ecosystem you detect (Gradle/Maven, npm/pnpm, pip/poetry, Go modules, Cargo, etc.).

## Language

- **User-facing replies and reasoning in chat:** Russian.
- **All durable text written into the knowledge graph via MCP** (`storeKnowledge`, factual `registerDependency` reasons, `markIndexingComplete` summaries, and similar): **English only** (clear, concise, searchable).

## Cursor `call_mcp_tool`: which `server` string to use

In Cursor’s agent/composer bridge, **`server` is often not** the short key from `mcp.json` (e.g. `AutoLinkingBrain`). If the host returns **“MCP server does not exist”**, use one of these forms instead (copy the exact id from MCP / agent logs or the on-disk MCP descriptor if needed):

1. **Global server** (entry in `%USERPROFILE%\.cursor\mcp.json`): use  
   **`user-<McpServersKey>`**  
   Example: **`user-AutoLinkingBrain`**.
2. **Project-scoped server** (workspace `.cursor/mcp.json` or merged project config): use  
   **`project-<n>-<workspaceFolderBasename>-<McpServersKey>`**  
   Example when the repo root folder is `mcp_server`: **`project-0-mcp_server-AutoLinkingBrain`**.  
   The index **`<n>`** or basename can differ per window; if a call fails, re-read the current id from logs/UI.

Prefer **one** MCP registration (usually **global** + `"cwd": "${workspaceFolder}"`) so the stable id **`user-AutoLinkingBrain`** is enough across repos.

**CodeGraph** (if configured in the same `mcp.json`): MCP server id is typically **`user-codegraph`**. Requires `.codegraph/` in the workspace (`codegraph init -i` once per repo).

## Dual MCP routing (CodeGraph + AutoLinkingBrain)

When **both** servers are available, route by intent — do not duplicate work with grep/read if CodeGraph already answers:

| Question type | Use first | Examples |
|---|---|---|
| Indexing state, incoming cross-repo deps, reindex | **AutoLinkingBrain** | `checkProjectHealth`, `sessionContextPack` |
| Prior decisions, documented architecture, bugfixes | **AutoLinkingBrain** | `retrieveChain`, `storeKnowledge` |
| Cross-repo outbound links during indexing | **AutoLinkingBrain** | `registerDependency`, `markIndexingComplete` |
| Symbol location, callers/callees, trace A→B, impact | **CodeGraph** | `codegraph_search`, `codegraph_trace`, `codegraph_explore`, `codegraph_impact` |
| File tree from index | **CodeGraph** | `codegraph_files` |

**Combined workflow for repo overview:**
1. `checkProjectHealth` (AutoLinkingBrain) — STATUS / INCOMING DEPENDENCIES.
2. Optional `sessionContextPack` or `retrieveChain` — semantic memory.
3. CodeGraph for structural questions (entry points, call flow) if `.codegraph/` exists.
4. Raw `read_file` / `grep` only for gaps (recent edits, stale index banner, or no index).

If CodeGraph returns "not initialized": offer `codegraph init -i` in the project root (or run `scripts/init_codegraph_project.ps1`).

## Mem0-first project analysis (graph before files)

When the user asks (in any wording) for a **repository / project** picture: overview, description, stack, architecture, “what is this project”, onboarding, high-level analysis of the **opened workspace** — treat this as **graph-first**, not file-first.

1. **Before any** `read_file`, `list_dir`, `grep`, `glob_file_search`, `codebase_search`, or similar filesystem/search tools: invoke MCP **`checkProjectHealth`** once with arguments **`{}`** and the **`server`** string from the section **«Cursor `call_mcp_tool`»** above (prefer **`user-AutoLinkingBrain`** when using global `mcp.json` with `"cwd": "${workspaceFolder}"`).
2. In the same turn, **interpret** `STATUS`, `REINDEX_PROTOCOL`, and **INCOMING DEPENDENCIES** from that response (summarize in **Russian** for the user).
3. Only **after** steps 1–2, optionally call **`sessionContextPack`** or **`retrieveChain`** if broader recall is needed, **then** open local files as needed.
4. Text injected by the Cursor **`sessionStart`** hook as **`additional_context`** already comes from Mem0 — treat it as **supplementary context**. It **does not** replace **`checkProjectHealth`** for **indexing state**, **`REINDEX_PROTOCOL`**, or **incoming dependency links**.

If **`checkProjectHealth`** fails or MCP is unavailable: state that clearly in **Russian** in one short sentence, then continue with file-based analysis **without** implying Mem0 health was checked.

## 1. Initialization & auto-discovery

**First action after opening a project:** call **`checkProjectHealth()`** (via MCP) and interpret the result.

- If **INCOMING DEPENDENCIES** list real links (other projects rely on this one): treat public surfaces as contracts — document them and avoid breaking changes without an explicit migration plan.
- If **`REINDEX_PROTOCOL: required`** (includes `STATUS: NEEDS_FULL_INDEXING`, mark stale per server rules, or unreadable `completed_at`):
  1. **Scan internal module boundaries:** e.g. Gradle `project(":…")`, Maven multi-module `<module>`, npm/pnpm workspaces, Go replace directives, Cargo workspace members, etc.
  2. **Scan outbound API/module dependencies:** HTTP clients (Ktor, Retrofit, OkHttp, `requests`, `httpx`, `fetch`, axios, etc.), OpenAPI/Swagger specs, gRPC protos, message schemas, shared DTO packages.
  3. For each dependency found, call **`registerDependency(target_project="…", link_type="module" OR "api", reason="…")`** with **English, factual** reasons.
  4. Scan main entrypoints, configs, and integration surfaces relevant to this stack.
  5. Call **`storeKnowledge`** with a **project** summary (`scope="project"` or `both` as appropriate), with correct `tech` / `scenario` labels — **body in English**.
  6. Finish with **`markIndexingComplete(summary="…")`** (**English** summary) so **`checkProjectHealth`** can see **`FINAL_INDEXING_MARK`**.
- Optionally, after a successful mark, call **`checkProjectHealth()`** once more if the user wants confirmation that reindex is no longer required.

## 2. Dependency contract

When changing behavior consumed by another project (shared models, REST/gRPC contracts, public modules, event payloads):

- **Before editing:** call **`retrieveChain`** with `linked_projects=["<dependent_slug>"]` (and `check_global` as needed). **Do not invent** tool output; if the tool returns nothing, say so and proceed cautiously.

## 3. Fact storage (`storeKnowledge`)

- **`tech`:** concrete stack tokens (e.g. Kotlin, Ktor, Spring, Node, Python, FastAPI).
- **`scenario`:** e.g. architecture, bugfix, api_contract, indexing.
- **`scope`:** `project` | `global` | `both`.
- **Memory body:** English.

## 4. Tool-use discipline

- For architecture, public API, cross-repo contracts, or “what we already stored”: **prefer MCP first** (`checkProjectHealth`, `retrieveChain`, `storeKnowledge` as needed), then answer.
- For **any project/repo analysis** (see **«Mem0-first project analysis»** above): **mandatory first MCP step** is **`checkProjectHealth`** before filesystem tools.
- If MCP tools are **unavailable or error**: state that clearly in Russian; do **not** fabricate health/mark output. Continue with local analysis only, without claiming Mem0 was updated.
- When calling MCP from the agent, use the **`server`** id from **«Cursor `call_mcp_tool`»** (often **`user-…`** or **`project-…`**, not the bare `mcp.json` key).

## 5. `linked_projects` convention

- Use **stable repo slugs** as in `project_<slug>` (directory name or the same slug used in topology), **no file paths**. If unsure, ask the user once instead of guessing.

## 6. Token discipline (MCP)

- Prefer **`sessionContextPack`** once at the start of substantive work instead of chaining **`checkProjectHealth`** + **`retrieveChain`** with overlapping goals.
- For targeted facts, use **`retrieveChain`** with a **narrow `query`**, `top_k_per_scope` ≤ 8 unless you truly need more, and keep `per_memory_chars` modest (e.g. 800–1200).
- For **`checkProjectHealth`**, rely on default caps; widen `max_response_chars` only when debugging.
- Do not paste full tool outputs back into the chat verbatim unless necessary; summarize in Russian for the user, keep English in Mem0 writes only.
- After protocol reindex, optionally call **`checkProjectHealth`** once; avoid repeated health calls in the same turn without new edits.
