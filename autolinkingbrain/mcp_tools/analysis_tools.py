"""MCP tool: runProjectAnalysis."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.project_analysis import evaluate_analysis_status, run_analysis_batch


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
        Run full or incremental project analysis batch. mode: auto|full|incremental.
        Uses heuristic composer (no LLM). Call repeatedly until next=done.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        pid, _ = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        root = (project_root or "").strip() or os.getcwd()
        batch = max_entities_per_call or int(os.environ.get("MEM0_ANALYSIS_BATCH_SIZE", "5"))

        def _add(text: str, uid: str) -> None:
            mctx.mem_add(text, uid, infer=False, source="mcp:runProjectAnalysis")

        result = run_analysis_batch(
            mctx.db,
            project_root=root,
            project_slug=pid,
            mode=mode,
            max_entities=batch,
            mem_add=_add,
        )
        status = evaluate_analysis_status(
            mctx.db,
            project_root=root,
            project_slug=pid,
            auto_run=os.environ.get("MEM0_ANALYSIS_AUTO_RUN", "1").strip().lower() not in ("0", "false"),
        )
        return json.dumps({"batch": result, "analysis_status": status.format_block()}, ensure_ascii=False, indent=2)
