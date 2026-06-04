"""MCP tool: runProjectAnalysis (single batch; prefer syncProjectIndex for full reindex)."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.project_analysis import evaluate_analysis_status, run_analysis_batch
from autolinkingbrain.project_sync import analysis_subprocess_enabled, run_index_subprocess


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="runProjectAnalysis")
    async def run_project_analysis(
        mode: str = "auto",
        max_entities_per_call: int = 0,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        One analysis batch only. For full reindex use syncProjectIndex or syncAllProjects.

        Runs in a subprocess on Windows by default so MCP stays connected.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        pid, _ = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        root = (project_root or "").strip() or os.getcwd()
        batch = max_entities_per_call or int(os.environ.get("MEM0_ANALYSIS_BATCH_SIZE", "5"))

        if analysis_subprocess_enabled():
            out = run_index_subprocess(
                root,
                mode=mode,
                batch_size=batch,
                index_only=True,
                until_done=False,
            )
            out["hint"] = "For full index until done, call syncProjectIndex instead of looping this tool."
            return json.dumps(out, ensure_ascii=False, indent=2)

        result = run_analysis_batch(
            None,
            project_root=root,
            project_slug=pid,
            mode=mode,
            max_entities=batch,
            mem_add=None,
        )
        status = evaluate_analysis_status(
            None,
            project_root=root,
            project_slug=pid,
            auto_run=os.environ.get("MEM0_ANALYSIS_AUTO_RUN", "1").strip().lower() not in ("0", "false"),
        )
        return json.dumps(
            {
                "batch": result,
                "analysis_status": status.format_block(),
                "hint": "For full index until done, call syncProjectIndex.",
            },
            ensure_ascii=False,
            indent=2,
        )
