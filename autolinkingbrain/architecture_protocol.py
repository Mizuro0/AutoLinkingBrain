"""Module-by-module architecture runs via local Ollama (Qwen) + handoff signals for the host agent."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autolinkingbrain.architecture_context import get_architecture_doc_path
from autolinkingbrain.architecture_doc import merge_section, read_doc
from autolinkingbrain.ollama_client import chat, is_available, review_model

PROTOCOL_VERSION = 1

_SECTIONS = ("modules", "apis", "dataflow", "integrations")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def architect_model() -> str:
    return (
        os.environ.get("OLLAMA_ARCHITECT_MODEL", "").strip()
        or os.environ.get("OLLAMA_REVIEW_MODEL", "").strip()
        or review_model()
    )


def architect_timeout_sec() -> int:
    raw = os.environ.get("OLLAMA_ARCHITECT_TIMEOUT_SEC", "180").strip()
    try:
        return max(30, min(int(raw), 600))
    except ValueError:
        return 180


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_slug(module: str) -> str:
    slug = (module or "").strip().lower().replace(" ", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    if not slug or not _SLUG_RE.match(slug):
        raise ValueError(f"invalid module slug: {module!r}")
    return slug


def architecture_dir(project_root: Path | str) -> Path:
    return Path(project_root).expanduser().resolve() / "docs" / "architecture"


def modules_dir(project_root: Path | str) -> Path:
    return architecture_dir(project_root) / "modules"


def module_artifact_path(project_root: Path | str, module: str) -> Path:
    return modules_dir(project_root) / f"{_normalize_slug(module)}.md"


def handoff_path(project_root: Path | str) -> Path:
    return Path(project_root).expanduser().resolve() / ".brain" / "architecture" / "handoff.json"


def run_manifest_path(project_root: Path | str) -> Path:
    return Path(project_root).expanduser().resolve() / ".brain" / "architecture" / "run.json"


def protocol_doc_path(project_root: Path | str) -> Path:
    return architecture_dir(project_root) / "README.md"


_ARCHITECT_SYSTEM = """You are a software architect using a small local LLM.
Output markdown ONLY (no JSON). Use these exact level-2 headers when present in the task:
## Summary
## Boundaries
## modules
## apis
## dataflow
## integrations
## Dependencies
## Risks
## open_questions

Under ## open_questions use bullets starting with "Q:" for anything uncertain or needing agent/code inspection.
Be concise. Do not invent file paths absent from the provided context.
English only for technical content."""


@dataclass
class ArchitectureRun:
    run_id: str
    project_root: str
    modules: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    current: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "run_id": self.run_id,
            "project_root": self.project_root,
            "modules": self.modules,
            "completed": self.completed,
            "current": self.current,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArchitectureRun:
        return cls(
            run_id=str(data.get("run_id") or ""),
            project_root=str(data.get("project_root") or ""),
            modules=list(data.get("modules") or []),
            completed=list(data.get("completed") or []),
            current=data.get("current"),
            created_at=str(data.get("created_at") or _now_iso()),
            updated_at=str(data.get("updated_at") or _now_iso()),
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def ensure_protocol_readme(project_root: Path | str) -> Path:
    root = Path(project_root).expanduser().resolve()
    readme = protocol_doc_path(root)
    if readme.is_file():
        return readme
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "\n".join(
            [
                "# Architecture modules (Ollama architect)",
                "",
                "Per-module artifacts: `modules/<slug>.md`",
                "Handoff signal for the host agent: `../../.brain/architecture/handoff.json`",
                "",
                "See `docs/ARCHITECTURE_AGENT_PROTOCOL.md` in the Brain repo for the workflow.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return readme


def start_run(
    project_root: Path | str,
    modules: list[str],
    *,
    run_id: str | None = None,
) -> ArchitectureRun:
    root = Path(project_root).expanduser().resolve()
    slugs = [_normalize_slug(m) for m in modules if (m or "").strip()]
    if not slugs:
        raise ValueError("modules list is empty")
    rid = (run_id or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = ArchitectureRun(run_id=rid, project_root=str(root), modules=slugs, current=slugs[0])
    _write_json(run_manifest_path(root), run.to_dict())
    ensure_protocol_readme(root)
    _write_handoff(
        root,
        {
            "signal": "run_started",
            "run_id": rid,
            "module": slugs[0],
            "message": f"Architecture run started. Process modules one at a time: {', '.join(slugs)}",
            "queue": slugs,
            "next_suggested_action": "runArchitectModule",
        },
    )
    return run


def load_run(project_root: Path | str) -> ArchitectureRun | None:
    data = _read_json(run_manifest_path(project_root))
    if not data:
        return None
    return ArchitectureRun.from_dict(data)


def _parse_open_questions(body: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    in_section = False
    q_idx = 0
    for line in body.splitlines():
        low = line.strip().lower()
        if low.startswith("## open_questions"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        text = line.strip()
        if text.lower().startswith("q:"):
            text = text[2:].strip()
        if text.startswith("- "):
            text = text[2:].strip()
        if not text:
            continue
        q_idx += 1
        blocking = "blocking" in text.lower() or "?" in text
        out.append({"id": f"Q{q_idx}", "text": text, "blocking": blocking})
    return out


def _build_module_markdown(
    *,
    module: str,
    run_id: str,
    section_focus: str,
    architect_body: str,
    context_preview: str,
) -> str:
    open_q = _parse_open_questions(architect_body)
    front = {
        "protocol_version": PROTOCOL_VERSION,
        "module": module,
        "run_id": run_id,
        "architect_status": "ready_for_agent",
        "section_focus": section_focus,
        "updated_at": _now_iso(),
        "open_questions": open_q,
        "agent_status": "pending",
    }
    return "\n".join(
        [
            "---",
            json.dumps(front, ensure_ascii=False, indent=2),
            "---",
            "",
            f"# Architecture: {module}",
            "",
            "## Context used (preview)",
            context_preview[:2000] or "(none)",
            "",
            architect_body.strip(),
            "",
            "## agent_review",
            "_Host agent: read sections above, answer open_questions, add execution notes._",
            "",
            "```yaml",
            "agent_status: pending  # pending | in_progress | blocked | done",
            "agent_notes: []",
            "resolved_questions: []",
            "```",
            "",
            "## execution_checklist",
            "- [ ] Read ## Summary and ## Boundaries",
            "- [ ] Resolve ## open_questions (or mark blocked)",
            "- [ ] Implement / verify per ## modules / ## apis",
            "- [ ] storeKnowledge summary fact when done",
            "",
        ]
    )


def _write_handoff(project_root: Path | str, payload: dict[str, Any]) -> Path:
    root = Path(project_root).expanduser().resolve()
    path = handoff_path(root)
    body = {
        "protocol_version": PROTOCOL_VERSION,
        "updated_at": _now_iso(),
        **payload,
    }
    if "artifact_path" not in body and body.get("module"):
        rel = module_artifact_path(root, str(body["module"]))
        try:
            body["artifact_path"] = str(rel.relative_to(root)).replace("\\", "/")
        except ValueError:
            body["artifact_path"] = str(rel)
    _write_json(path, body)
    return path


def read_handoff(project_root: Path | str) -> dict[str, Any]:
    data = _read_json(handoff_path(project_root))
    return data or {"signal": "none", "message": "No architecture handoff yet."}


def run_architect_module(
    project_root: Path | str,
    *,
    module: str,
    context: str,
    section_focus: str = "all",
    mem_snippets: list[str] | None = None,
    code_hints: list[str] | None = None,
) -> dict[str, Any]:
    """Call Ollama, write module MD, emit handoff signal."""
    root = Path(project_root).expanduser().resolve()
    slug = _normalize_slug(module)
    focus = (section_focus or "all").strip().lower()
    if focus not in ("all", *_SECTIONS):
        focus = "all"

    if not is_available():
        return {
            "ok": False,
            "error": "ollama_unavailable",
            "hint": "Run: ollama serve && ollama pull " + architect_model(),
        }

    run = load_run(root)
    run_id = run.run_id if run else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    snippets = "\n".join(f"- {s[:500]}" for s in (mem_snippets or []))
    hints = "\n".join(f"- {h[:400]}" for h in (code_hints or []))
    ctx = (context or "").strip()
    max_ctx = int(os.environ.get("ARCHITECT_CONTEXT_MAX_CHARS", "10000"))
    if len(ctx) > max_ctx:
        ctx = ctx[: max_ctx - 40] + "\n… [truncated]"

    task = (
        f"Module slug: {slug}\n"
        f"Section focus: {focus}\n\n"
        f"## Agent-provided context\n{ctx or '(none)'}\n\n"
        f"## Mem0 snippets\n{snippets or '(none)'}\n\n"
        f"## Code hints\n{hints or '(none)'}\n\n"
        "Produce architecture markdown for this module only."
    )
    if focus != "all":
        task += f" Emphasize ## {focus} section; keep other sections brief."

    try:
        architect_body = chat(
            task,
            system=_ARCHITECT_SYSTEM,
            model=architect_model(),
            temperature=0.15,
            timeout_sec=architect_timeout_sec(),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "module": slug}

    artifact = module_artifact_path(root, slug)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    preview = ctx[:800]
    artifact.write_text(
        _build_module_markdown(
            module=slug,
            run_id=run_id,
            section_focus=focus,
            architect_body=architect_body,
            context_preview=preview,
        ),
        encoding="utf-8",
    )

    open_q = _parse_open_questions(architect_body)
    if run:
        if slug not in run.completed:
            run.completed.append(slug)
        remaining = [m for m in run.modules if m not in run.completed]
        run.current = remaining[0] if remaining else None
        run.updated_at = _now_iso()
        _write_json(run_manifest_path(root), run.to_dict())

    handoff = _write_handoff(
        root,
        {
            "signal": "module_ready",
            "run_id": run_id,
            "module": slug,
            "architect_status": "ready_for_agent",
            "message": (
                f"Architect (Ollama/{architect_model()}) finished module `{slug}`. "
                "Host agent MUST read artifact_path and fill ## agent_review."
            ),
            "open_questions": open_q,
            "section_focus": focus,
            "next_suggested_action": "read_artifact_and_review",
            "ollama_model": architect_model(),
        },
    )

    return {
        "ok": True,
        "module": slug,
        "run_id": run_id,
        "artifact_path": str(artifact.relative_to(root)).replace("\\", "/"),
        "handoff_path": str(handoff.relative_to(root)).replace("\\", "/"),
        "open_questions_count": len(open_q),
        "signal": "module_ready",
        "next_module": run.current if run else None,
    }


def record_agent_review(
    project_root: Path | str,
    *,
    module: str,
    agent_status: str,
    agent_notes: str = "",
    resolved_questions: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    slug = _normalize_slug(module)
    path = module_artifact_path(root, slug)
    if not path.is_file():
        return {"ok": False, "error": f"missing artifact {path}"}

    text = path.read_text(encoding="utf-8")
    status = (agent_status or "in_progress").strip().lower()
    if status not in ("pending", "in_progress", "blocked", "done"):
        status = "in_progress"

    block = [
        "## agent_review",
        f"**agent_status:** {status}",
        f"**updated_at:** {_now_iso()}",
        "",
        (agent_notes or "").strip() or "(no notes)",
        "",
    ]
    if resolved_questions:
        block.append("**resolved_questions:**")
        for q in resolved_questions:
            block.append(f"- {q}")
        block.append("")

    if "## agent_review" in text:
        head, _, tail = text.partition("## agent_review")
        tail = tail.split("## execution_checklist", 1)
        rest = "## execution_checklist" + tail[1] if len(tail) > 1 else ""
        text = head + "\n".join(block) + "\n" + rest
    else:
        text = text.rstrip() + "\n\n" + "\n".join(block)

    path.write_text(text, encoding="utf-8")
    _write_handoff(
        root,
        {
            "signal": "agent_review_recorded",
            "module": slug,
            "agent_status": status,
            "message": f"Agent review recorded for `{slug}`. Status={status}.",
            "artifact_path": str(path.relative_to(root)).replace("\\", "/"),
            "next_suggested_action": "continue_next_module" if status == "done" else "resolve_open_questions",
        },
    )
    return {"ok": True, "module": slug, "agent_status": status, "artifact_path": str(path)}


def rollup_to_generated_doc(project_root: Path | str, *, module: str) -> str:
    """Merge one module artifact into docs/ARCHITECTURE.generated.md (modules section)."""
    root = Path(project_root).expanduser().resolve()
    slug = _normalize_slug(module)
    artifact = module_artifact_path(root, slug)
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    body = artifact.read_text(encoding="utf-8")
    doc_path = get_architecture_doc_path(root)
    block = f"\n\n### Feature: {slug}\n\n{body}\n"
    merge_section(doc_path, "modules", block, project_slug="")
    return f"Rolled up `{slug}` into {doc_path}"


def protocol_summary() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "architect_backend": "ollama",
        "model": architect_model(),
        "workflow": [
            "planArchitectureRun(modules[])",
            "Per module: CodeGraph + Brain context → runArchitectModule(context, section_focus)",
            "getArchitectHandoff → read artifact_path MD",
            "recordAgentArchitectureReview(notes, status)",
            "rollupArchitectureModule when module done",
        ],
        "artifact_pattern": "docs/architecture/modules/<slug>.md",
        "handoff_pattern": ".brain/architecture/handoff.json",
        "section_focus": ["all", *_SECTIONS],
        "agent_status_values": ["pending", "in_progress", "blocked", "done"],
    }
