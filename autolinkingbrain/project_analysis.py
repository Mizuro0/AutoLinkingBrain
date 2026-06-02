"""Project analysis orchestrator — full/incremental batches."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from autolinkingbrain.brain_record_composer import compose_entity_fact, infer_code_role
from autolinkingbrain.indexing_coverage import (
    analyze_indexing_coverage,
    load_project_memory_texts,
    load_topology_memory_texts,
)
from autolinkingbrain.project_index_state import ProjectIndexState


@dataclass
class AnalysisStatus:
    state: str  # ok | required_full | required_incremental | running
    auto_run: bool
    reason: str
    entity_count: int = 0
    stale_count: int = 0

    def format_block(self) -> str:
        auto = "AUTO_RUN: yes" if self.auto_run else "AUTO_RUN: no"
        return (
            f"STATUS: {self.state}\n"
            f"REASON: {self.reason}\n"
            f"ENTITIES: {self.entity_count} | STALE_QUEUE: {self.stale_count}\n"
            f"{auto}"
        )


def evaluate_analysis_status(
    db,
    *,
    project_root: Path | str,
    project_slug: str,
    auto_run: bool = True,
) -> AnalysisStatus:
    uid = f"project_{project_slug}"
    texts = load_project_memory_texts(db, uid)
    topo = load_topology_memory_texts(db)
    cov = analyze_indexing_coverage(texts, topo, project_slug)
    state = ProjectIndexState(project_root)
    entities = state.list_entities()
    stale = state.stale_paths()
    if not texts or not cov.sufficient:
        return AnalysisStatus(
            state="required_full",
            auto_run=auto_run,
            reason="Mem0 empty or coverage insufficient",
            entity_count=len(entities),
            stale_count=len(stale),
        )
    if stale:
        return AnalysisStatus(
            state="required_incremental",
            auto_run=auto_run,
            reason=f"{len(stale)} stale entities in queue",
            entity_count=len(entities),
            stale_count=len(stale),
        )
    if not entities:
        return AnalysisStatus(
            state="required_full",
            auto_run=auto_run,
            reason="No index state DB entities",
            entity_count=0,
            stale_count=0,
        )
    return AnalysisStatus(
        state="ok",
        auto_run=False,
        reason="Index state and coverage OK",
        entity_count=len(entities),
        stale_count=len(stale),
    )


def run_analysis_batch(
    db,
    *,
    project_root: Path | str,
    project_slug: str,
    mode: str = "auto",
    max_entities: int | None = None,
    mem_add: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    batch = max_entities or int(os.environ.get("MEM0_ANALYSIS_BATCH_SIZE", "5"))
    status = evaluate_analysis_status(db, project_root=root, project_slug=project_slug)
    effective_mode = mode
    if mode == "auto":
        effective_mode = "full" if status.state == "required_full" else "incremental"

    state = ProjectIndexState(root)
    run_id = state.start_run(effective_mode)
    files = state.scan_source_files()
    if effective_mode == "incremental":
        targets, _unchanged = state.detect_changes(files)
    else:
        targets = files

    processed = 0
    stored = 0
    uid = f"project_{project_slug}"

    for path, rel in targets[:batch]:
        try:
            digest = state.file_sha256(path)
            hint = path.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            continue
        role = infer_code_role(rel, hint)
        fact = compose_entity_fact(path=rel, summary=f"Indexed source `{rel}`.", code_role=role, content_hint=hint)
        state.upsert_entity(rel, digest, role)
        if mem_add:
            mem_add(fact.enriched(), uid)
            stored += 1
        processed += 1

    state.finish_run(run_id, entities_processed=processed, status="ok")
    state.export_markdown()
    state.close()

    remaining = max(0, len(targets) - batch)
    next_mode = effective_mode if remaining else "ok"
    return {
        "mode": effective_mode,
        "processed": processed,
        "stored": stored,
        "remaining_estimate": remaining,
        "next": "continue" if remaining else "done",
        "status_after": evaluate_analysis_status(db, project_root=root, project_slug=project_slug).state,
    }
