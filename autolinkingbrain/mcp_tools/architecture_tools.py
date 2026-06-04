"""ArchitectureCurator MCP — Ollama (Qwen) module architect + handoff signals."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from autolinkingbrain.architecture_context import architecture_budget, build_module_context, get_architecture_doc_path
from autolinkingbrain.architecture_curator import section_status, update_section
from autolinkingbrain.architecture_doc import read_doc
from autolinkingbrain.architecture_protocol import (
    architect_model,
    load_run,
    protocol_summary,
    read_handoff,
    record_agent_review,
    rollup_to_generated_doc,
    run_architect_module,
    start_run,
)
from autolinkingbrain.ollama_client import is_available


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="getArchitectProtocol")
    async def get_architect_protocol() -> str:
        """
        Shared language between Ollama architect and host agent: paths, signals, workflow.
        Call first when starting feature architecture work.
        """
        summary = protocol_summary()
        summary["ollama_available"] = is_available()
        return json.dumps(summary, ensure_ascii=False, indent=2)

    @mcp.tool(name="planArchitectureRun")
    async def plan_architecture_run(
        modules: list[str],
        project_root: str = "",
        run_id: str = "",
    ) -> str:
        """
        Start a multi-module architecture run (queue). Process one module per runArchitectModule call.

        modules: kebab-case slugs, e.g. ["online-booking", "billing-export"].
        """
        root = (project_root or os.getcwd()).strip()
        if not modules:
            return json.dumps({"ok": False, "error": "modules list required"}, indent=2)
        try:
            run = start_run(root, modules, run_id=run_id or None)
            return json.dumps(
                {
                    "ok": True,
                    "run": run.to_dict(),
                    "handoff": read_handoff(root),
                    "hint": "Next: runArchitectModule for each module with Brain+CodeGraph context.",
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, indent=2)

    @mcp.tool(name="runArchitectModule")
    async def run_architect_module_tool(
        module: str,
        context: str,
        section_focus: str = "all",
        mem_snippets: list[str] | None = None,
        code_hints: list[str] | None = None,
        project_root: str = "",
    ) -> str:
        """
        Local Ollama (Qwen) drafts one module architecture MD file.

        Host agent supplies `context` (CodeGraph trace, file paths, decisions) — keep under budget.
        section_focus: all | modules | apis | dataflow | integrations.
        On success: read getArchitectHandoff → open artifact_path.
        """
        root = (project_root or os.getcwd()).strip()
        out = run_architect_module(
            root,
            module=module,
            context=context,
            section_focus=section_focus,
            mem_snippets=mem_snippets,
            code_hints=code_hints,
        )
        return json.dumps(out, ensure_ascii=False, indent=2)

    @mcp.tool(name="getArchitectHandoff")
    async def get_architect_handoff(project_root: str = "") -> str:
        """
        Signal for the calling agent: where to read architect output and what to do next.

        Always call after runArchitectModule before implementing code.
        """
        root = (project_root or os.getcwd()).strip()
        handoff = read_handoff(root)
        run = load_run(root)
        payload = {"handoff": handoff}
        if run:
            payload["run"] = run.to_dict()
        payload["model"] = architect_model()
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.tool(name="recordAgentArchitectureReview")
    async def record_agent_architecture_review(
        module: str,
        agent_status: str,
        agent_notes: str = "",
        resolved_questions: list[str] | None = None,
        project_root: str = "",
    ) -> str:
        """
        Host agent records review/execution notes in the module MD (## agent_review).

        agent_status: pending | in_progress | blocked | done.
        """
        root = (project_root or os.getcwd()).strip()
        out = record_agent_review(
            root,
            module=module,
            agent_status=agent_status,
            agent_notes=agent_notes,
            resolved_questions=resolved_questions,
        )
        return json.dumps(out, ensure_ascii=False, indent=2)

    @mcp.tool(name="rollupArchitectureModule")
    async def rollup_architecture_module(module: str, project_root: str = "") -> str:
        """Append module artifact into docs/ARCHITECTURE.generated.md (modules section)."""
        root = (project_root or os.getcwd()).strip()
        try:
            msg = rollup_to_generated_doc(root, module=module)
            return json.dumps({"ok": True, "message": msg}, indent=2)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, indent=2)

    # --- Legacy incremental doc tools (optional rollup path) ---

    @mcp.tool(name="getArchitectureDoc")
    async def get_architecture_doc(project_root: str = "") -> str:
        """Read docs/ARCHITECTURE.generated.md for project."""
        root = (project_root or os.getcwd()).strip()
        path = get_architecture_doc_path(root)
        return read_doc(path)

    @mcp.tool(name="updateArchitectureSection")
    async def update_architecture_section(
        section_id: str,
        content: str,
        project_root: str = "",
        project_slug: str = "",
        module: str = "",
    ) -> str:
        """Legacy: update one section manually (prefer runArchitectModule for Ollama drafts)."""
        root = (project_root or os.getcwd()).strip()
        return update_section(
            project_root=root,
            section_id=section_id,
            content=content,
            project_slug=project_slug,
            module=module,
        )

    @mcp.tool(name="getArchitectureBudget")
    async def get_architecture_budget() -> str:
        """Char budgets for module context and section focus."""
        budget = architecture_budget()
        budget["architect_model"] = architect_model()
        budget["module_context_max_chars"] = int(os.environ.get("ARCHITECT_CONTEXT_MAX_CHARS", "10000"))
        budget["ollama_available"] = is_available()
        budget["workflow"] = "module_by_module_via_runArchitectModule"
        return json.dumps(budget, indent=2)

    @mcp.tool(name="refreshArchitectureFromDiff")
    async def refresh_architecture_from_diff(project_root: str = "") -> str:
        """Report section hashes in ARCHITECTURE.generated.md."""
        root = (project_root or os.getcwd()).strip()
        st = section_status(root)
        return json.dumps(st, indent=2)

    @mcp.tool(name="buildArchitectureContext")
    async def build_architecture_context(module_name: str, project_root: str = "") -> str:
        """Assemble context template for the host agent before runArchitectModule."""
        root = (project_root or os.getcwd()).strip()
        return build_module_context(module_name=module_name, project_root=root)
