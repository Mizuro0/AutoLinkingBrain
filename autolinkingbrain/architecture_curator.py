"""Orchestrate architecture section updates."""

from __future__ import annotations

from pathlib import Path

from autolinkingbrain.architecture_context import build_module_context, get_architecture_doc_path
from autolinkingbrain.architecture_doc import merge_section, parse_sections, read_doc
from autolinkingbrain.brain_record_composer import compose_architecture_section


def update_section(
    *,
    project_root: Path | str,
    section_id: str,
    content: str,
    project_slug: str = "",
    module: str = "",
) -> str:
    doc_path = get_architecture_doc_path(project_root)
    sec = merge_section(doc_path, section_id, content, project_slug=project_slug)
    return f"Updated section `{sec.section_id}` hash={sec.hash} at {doc_path}"


def mem0_fact_for_section(section_id: str, content: str, module: str = "") -> str:
    fact = compose_architecture_section(section=section_id, content=content, module=module)
    return fact.enriched()


def section_status(project_root: Path | str) -> dict:
    doc_path = get_architecture_doc_path(project_root)
    text = read_doc(doc_path)
    sections = parse_sections(text)
    return {
        "path": str(doc_path),
        "sections": {
            sid: {"hash": sec.hash, "updated": sec.updated, "chars": len(sec.content)}
            for sid, sec in sections.items()
        },
    }


def build_context_for_module(
    *,
    module_name: str,
    project_root: Path | str,
    mem_snippets: list[str] | None = None,
) -> str:
    return build_module_context(
        module_name=module_name,
        project_root=project_root,
        mem_snippets=mem_snippets,
    )
