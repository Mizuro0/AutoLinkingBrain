"""Build module context for ArchitectureCurator (Mem0 + budget)."""

from __future__ import annotations

import os
from pathlib import Path


def get_architecture_doc_path(project_root: Path | str) -> Path:
    return Path(project_root).expanduser().resolve() / "docs" / "ARCHITECTURE.generated.md"


def build_module_context(
    *,
    module_name: str,
    project_root: Path | str,
    mem_snippets: list[str] | None = None,
    code_hints: list[str] | None = None,
    max_chars: int | None = None,
) -> str:
    budget = max_chars or int(os.environ.get("ARCH_CONTEXT_MAX_CHARS", "12000"))
    root = Path(project_root).expanduser().resolve()
    lines = [
        f"# Context for module: {module_name}",
        f"Project root: {root}",
        "",
        "## Mem0 snippets",
    ]
    for s in mem_snippets or []:
        lines.append(f"- {s[:600]}")
    if not mem_snippets:
        lines.append("(none)")
    lines.extend(["", "## Code hints"])
    for h in code_hints or []:
        lines.append(f"- {h[:400]}")
    if not code_hints:
        lines.append("(run CodeGraph for structure)")
    body = "\n".join(lines)
    if len(body) > budget:
        body = body[: budget - 40] + "\n… [truncated for budget]"
    return body


def architecture_budget(*, max_section_chars: int | None = None) -> dict:
    return {
        "max_section_chars": max_section_chars or int(os.environ.get("ARCH_SECTION_MAX_CHARS", "8000")),
        "sections": ["modules", "apis", "dataflow", "integrations"],
        "one_section_per_call": True,
    }
