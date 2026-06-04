---
name: architecture-by-feature
description: >-
  MANDATORY when user asks to compose/design architecture (составить архитектуру,
  спроектировать, архитектурный план, module map, ARCHITECTURE, слабые места в архитектуре).
  Cursor host agent: project analysis, weak spots, module boundaries, CodeGraph/Brain.
  ArchitectureCurator+Ollama Qwen: only per-module MD drafts (runArchitectModule).
  NOT for the small model to analyze the whole repo.
---

# Architecture by feature — roles

| Task | Who |
|------|-----|
| Анализ проекта, слабые места, риски, границы модулей, что вынести в очередь | **Host agent (Cursor)** — Brain, CodeGraph, чтение кода, рассуждение |
| Черновик MD по **одному** модулю (`modules/apis/…`) | **ArchitectureCurator** + Ollama (`runArchitectModule`) |
| Реализация, ответы на `Q:`, заметки | **Host agent** — `recordAgentArchitectureReview`, код |

MCP: **`user-ArchitectureCurator`**. Protocol: **`docs/ARCHITECTURE_AGENT_PROTOCOL.md`**.

Install: `python brain.py mcp install --scope global --profile full` + `ollama serve`.

## Triggers (always use this skill)

User says (RU/EN): *составить архитектуру*, *спроектировать*, *архитектурный план*, *описать модули*, *обновить архитектуру*, *design architecture*, *architecture doc*, *module boundaries*.

**Do not** let Ollama/Qwen scan the repo or find weak spots — **you** do that first, then pass a **short concrete `context`** per module.

## Phase A — Host agent only (before any `runArchitectModule`)

```
1. sessionContextPack / checkProjectHealth / retrieveChain   # Brain
2. codegraph_context, codegraph_impact, codegraph_trace      # structure
3. syncProjectIndex or code read — YOUR synthesis:
   - module list (kebab-case slugs) and why
   - weak spots / tech debt / coupling (bullets for the user)
   - what each module needs in section_focus (apis | dataflow | …)
4. Present module queue to user if scope is large (optional)
5. getArchitectProtocol
6. planArchitectureRun { modules: [...] }   # once
```

Index state: prefer **`syncProjectIndex`** / `brain.py analyze sync` — not MCP `runProjectAnalysis` loops.

## Phase B — One module per architect call (Ollama)

```
7. runArchitectModule {
     module: "<slug>",
     context: "<YOUR trace, paths, risks for THIS module only>",
     section_focus: "all" | "apis" | …
   }
8. getArchitectHandoff → READ docs/architecture/modules/<slug>.md
9. Resolve ## open_questions (Q:) — you + CodeGraph; blocked → ask user
10. recordAgentArchitectureReview { agent_status, agent_notes, resolved_questions }
11. Next module from run.json queue until done
12. rollupArchitectureModule (optional) + storeKnowledge per module
```

## Handoff signals (`.brain/architecture/handoff.json`)

| signal | Host agent |
|--------|------------|
| `module_ready` | Open `artifact_path` before coding |
| `run_started` | Start first `runArchitectModule` |

## Do not

- Delegate **project-wide analysis** or **weak-spot hunt** to `runArchitectModule`.
- Call `runArchitectModule` for multiple slugs in one turn.
- Skip reading MD after `module_ready`.
- Use legacy `updateArchitectureSection` for full feature design (manual edits only).

## Environment

`OLLAMA_ARCHITECT_MODEL` (default `qwen2.5-coder:7b`), `ARCHITECT_CONTEXT_MAX_CHARS=10000`.

## User phrase

> Составь архитектуру: **ты** проанализируй проект и слабые места, затем по протоколу Ollama — **по одному модулю** `runArchitectModule`, после каждого читай handoff MD.
