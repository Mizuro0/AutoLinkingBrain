---
name: mcp-triumvirate
description: >-
  Triumvirate workflow for Brain MCP projects: AutoLinkingBrain memory + CodeGraph
  structure + Matt Pocock alignment/TDD/diagnose (optional). Use for non-trivial
  features, ambiguous requirements, refactors, or when CONTEXT.md needs updating.
  Pair with autolinking-brain-mcp; do not replace it.
---

# MCP Triumvirate — Brain · CodeGraph · Discipline

Three roles, **one thin orchestration layer**. No ECC, no extra hooks.

| Pillar | Tool / skill | When |
|--------|----------------|------|
| **Memory & contracts** | AutoLinkingBrain (`sessionContextPack`, `retrieveChain`, `storeKnowledge`) | Every session |
| **Code structure** | CodeGraph (`codegraph_context`, `codegraph_trace`, `codegraph_impact`) | Implementation & refactor |
| **Feature architecture** | Skill `architecture-by-feature` — **you** analyze; Ollama drafts module MD | User asks to compose architecture, module map |
| **Human alignment** | Matt Pocock: `grill-with-docs`, `tdd`, `diagnose` (optional, user-installed) | Ambiguous scope, bugs, new vertical slices |

Read domain terms: repo root **`CONTEXT.md`**.

## Session flow

```
1. Recall     → sessionContextPack { recall_query: "<task keywords>" }
2. Align?     → if scope unclear: grill-with-docs (update CONTEXT.md + storeKnowledge glossary)
3. Structure  → CodeGraph before grep/read for "how / who calls / impact"
4. Contracts  → retrieveChain before shared API changes
5. Arch?      → user asks compose architecture: architecture-by-feature (you: analysis + weak spots; Ollama: one module per runArchitectModule)
6. Build      → tdd for features; diagnose for regressions
7. Persist    → storeKnowledge (English, file paths) after each decision
8. Review     → QwenReviewer on staged diff (optional)
```

## When to skip Pocock skills

- One-line fix with clear target file
- Health/recall already answer the task
- User said "no questions, just do it"

## When to run grill-with-docs

- New feature without acceptance criteria
- Refactor touching multiple modules
- Terminology drift (agent uses long prose instead of `CONTEXT.md` terms)

After grilling: add rows to `CONTEXT.md`; `storeKnowledge` one fact: `scenario: architecture`, scope `project`.

## Install Pocock skills (optional, once per machine)

From repo root:

```powershell
.\scripts\install-pocock-skills.ps1
```

```bash
./scripts/install-pocock-skills.sh
```

Installs only: `grill-with-docs`, `tdd`, `diagnose`, `setup-matt-pocock-skills` — not the full mattpocock catalog.

## Bloat guard

| Do | Don't |
|----|--------|
| Keep 2 alwaysApply Brain rules | Add triumvirate as alwaysApply |
| Selective Pocock skills (script) | `npx ecc-install --profile full` |
| `CONTEXT.md` + Mem0 facts | Duplicate memory in ECC hooks |
| This skill + `autolinking-brain-mcp` | Merge into one 500-line skill |

Full guide: [docs/TRIUMVIRATE.md](../../../docs/TRIUMVIRATE.md).
