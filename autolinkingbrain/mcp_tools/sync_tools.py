"""MCP tools: set-and-forget project indexing via subprocess (keeps brain_server alive)."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.project_sync import (
    analysis_subprocess_enabled,
    run_index_subprocess,
    sync_discovered_projects,
)


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="syncProjectIndex")
    async def sync_project_index(
        mode: str = "auto",
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        batch_size: int = 0,
        *,
        ctx: Context,
    ) -> str:
        """
        Full project index until done — runs in a subprocess (does not crash MCP).

        Updates .brain/project_index.db for the repo. Default: no per-file Mem0 spam.
        Prefer this over repeated runProjectAnalysis when user asks to refresh project info.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        pid, _ = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        root = (project_root or "").strip() or os.getcwd()
        bs = batch_size or int(os.environ.get("MEM0_ANALYSIS_BATCH_SIZE", "5"))
        if analysis_subprocess_enabled():
            out = run_index_subprocess(
                root,
                mode=mode,
                batch_size=bs,
                index_only=True,
            )
        else:
            from autolinkingbrain.project_sync import run_index_until_done

            out = run_index_until_done(root, mode=mode, batch_size=bs, index_only=True)
        out["project_slug"] = pid
        return json.dumps(out, ensure_ascii=False, indent=2)

    @mcp.tool(name="syncAllProjects")
    async def sync_all_projects(
        mode: str = "auto",
        extra_paths: str = "",
        batch_size: int = 0,
        *,
        ctx: Context,
    ) -> str:
        """
        Index every discovered repo (CodeGraph layout + optional extra_paths).

        Set-and-forget: subprocess per repo. Use when user asks to refresh all project info.
        extra_paths: semicolon-separated roots (e.g. D:/codes/backend;D:/codes/altey).
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        paths = [p.strip() for p in (extra_paths or "").replace("\n", ";").split(";") if p.strip()]
        bs = batch_size or int(os.environ.get("MEM0_ANALYSIS_BATCH_SIZE", "5"))
        out = sync_discovered_projects(
            extra_paths=paths,
            mode=mode,
            batch_size=bs,
            index_only=True,
        )
        return json.dumps(out, ensure_ascii=False, indent=2)
