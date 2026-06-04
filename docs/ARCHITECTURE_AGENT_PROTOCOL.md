# Architecture agent protocol (Ollama architect ↔ host agent)

Version **1**. Small local models (Qwen via Ollama) work **one module per call**; the host agent reads MD artifacts and executes in stages.

## Roles

| Role | Who | Output |
|------|-----|--------|
| **Architect** | ArchitectureCurator MCP + Ollama | `docs/architecture/modules/<slug>.md` |
| **Host agent** | Cursor / Claude / etc. | `## agent_review` in same file + code changes |
| **Signal** | `.brain/architecture/handoff.json` | Tells the agent *what to open next* |

## File layout (target repo)

```text
docs/architecture/
  README.md
  modules/
    online-booking.md
    billing-export.md
.brain/architecture/
  run.json          # queue: modules[], completed[]
  handoff.json      # last signal for the agent
docs/ARCHITECTURE.generated.md   # optional rollup
```

## Handoff signals

| signal | Meaning |
|--------|---------|
| `run_started` | Queue created — start first module |
| `module_ready` | Architect finished — **read `artifact_path`** |
| `agent_review_recorded` | Agent left notes — continue or next module |
| `none` | No run yet |

## MCP tool chain

```
getArchitectProtocol
planArchitectureRun { modules: ["slug-a", "slug-b"] }

# --- per module (repeat) ---
sessionContextPack / retrieveChain     # Brain
codegraph_context / codegraph_trace    # CodeGraph
buildArchitectureContext { module_name }
runArchitectModule {
  module: "slug-a",
  context: "<paste trace, paths, contracts>",
  section_focus: "apis"   # or all | modules | dataflow | integrations
}
getArchitectHandoff                    # → artifact_path
# Agent reads MD, implements, answers Q: items
recordAgentArchitectureReview {
  module: "slug-a",
  agent_status: "done",           # pending | in_progress | blocked | done
  agent_notes: "Resolved Q1: ...",
  resolved_questions: ["Q1"]
}
rollupArchitectureModule { module: "slug-a" }
storeKnowledge { scenario: architecture, text: "..." }
```

## Module MD structure (shared language)

Every `modules/<slug>.md` contains:

- YAML-like JSON frontmatter: `open_questions`, `architect_status`, `agent_status`
- `## Summary`, `## Boundaries`, section blocks (`## apis`, …)
- `## open_questions` — bullets `Q:` from architect
- `## agent_review` — **only the host agent writes here**
- `## execution_checklist` — tick during implementation

## Rules for the host agent

1. **Never** send multiple modules in one `runArchitectModule` call.
2. **Always** call `getArchitectHandoff` after architect run and **read the file** (do not rely on tool return JSON alone).
3. If `open_questions` has **blocking** items → `agent_status: blocked` until resolved (CodeGraph / user / Brain).
4. Pass **concrete** `context`: file paths, symbol names, dependency edges — not vague feature names.
5. `section_focus` narrows the small model on one slice (`apis` only, etc.).
6. After each module `done` → `storeKnowledge` one English fact with paths.

## Environment

| Variable | Default |
|----------|---------|
| `OLLAMA_ARCHITECT_MODEL` | `qwen2.5-coder:7b` |
| `OLLAMA_ARCHITECT_TIMEOUT_SEC` | `180` |
| `ARCHITECT_CONTEXT_MAX_CHARS` | `10000` |

Requires `ollama serve` on `127.0.0.1:11434`.

## Legacy

`updateArchitectureSection` / `getArchitectureDoc` still work for manual edits. Prefer the module pipeline for automated runs.
