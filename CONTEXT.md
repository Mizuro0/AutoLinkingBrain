# Shared language — AutoLinkingBrain (mcp_server)

Ubiquitous terms for agents and humans. Extend via `/grill-with-docs` or after `storeKnowledge` glossary facts.

| Term | Meaning |
|------|---------|
| **Brain** | AutoLinkingBrain MCP — Mem0/Chroma memory, health, analysis, cross-repo contracts |
| **CodeGraph** | Structural index (`.codegraph/`) — symbols, callers, trace, impact |
| **Triumvirate** | Brain + CodeGraph + discipline skills (grill / TDD / diagnose) — not a fourth MCP |
| **ArchitectureCurator** | MCP (profile `full`) — Ollama Qwen per-module MD + `.brain/architecture/handoff.json` |
| **Local install YAML** | `config/local/install.yaml` (gitignored) — per-device MCP profile; repo default stays `standard` |
| **Feature slice** | One feature loop: recall → CodeGraph → `buildArchitectureContext` → `updateArchitectureSection` → `storeKnowledge` |
| **Curated memory** | Facts from `storeKnowledge` / `runProjectAnalysis` — architecture truth |
| **Generated arch doc** | `ARCHITECTURE.generated.md` — artifact; pair with `storeKnowledge` for recall |
| **Autolog** | Hook-written session noise — not architecture truth (`facts_only`) |
| **Session pack** | `sessionContextPack` — health + recall in one call |
| **Indexing mark** | `markIndexingComplete` — only tool that sets FINAL_INDEXING |
| **Channel** | Mem0 `user_id`: `project_<slug>`, `global_skills`, `global_topology` |
| **Harness** | Cursor (agent + MCP + hooks) — not the application runtime |

## Anti-patterns (do not say)

- "Search the repo first" for architecture → use Brain then CodeGraph
- "Remember in chat" for decisions → `storeKnowledge`
- Installing full ECC on top of Brain → duplicate memory/hooks
