"""MCP tools: session autolog in SQLite (separate from curated Mem0 facts)."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.autolog_store import list_recent, resolve_db_path, search_entries
from autolinkingbrain.mcp_context import McpContext


def _format_rows(rows: list[dict], *, preview_chars: int) -> str:
    if not rows:
        return "No session autolog entries (SQLite `.cursor/autolog.db`)."
    lines: list[str] = []
    for row in rows:
        body = (row.get("body") or "").replace("\n", " ")
        if len(body) > preview_chars:
            body = body[: preview_chars - 3] + "…"
        lines.append(
            f"• id={row.get('id')} | {row.get('created_at', '')} | "
            f"project={row.get('project_slug')} | hook={row.get('hook')}\n  {body}"
        )
    return "\n".join(lines)


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="listSessionAutolog")
    async def list_session_autolog(
        limit: int = 25,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        preview_chars: int = 400,
        *,
        ctx: Context,
    ) -> str:
        """
        Recent substantive session logs from SQLite autolog archive — NOT curated Mem0 facts.

        Hooks write here by default (MEM0_AUTOLOG_BACKEND=sqlite). Use when you need
        prior session narrative, debugging arc, or what was tried — not architecture truth.
        For decisions and patterns use retrieveChain / storeKnowledge instead.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        limit = max(1, min(limit, 100))
        preview_chars = max(80, min(preview_chars, 1200))
        root = Path((project_root or "").strip() or os.getcwd())
        pid, _ = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        db_path = resolve_db_path(workspace_root=root)
        rows = list_recent(pid, limit=limit, db_path=db_path)
        header = f"# Session autolog — `{db_path}` — project `{pid}` ({len(rows)} rows)\n\n"
        return header + _format_rows(rows, preview_chars=preview_chars)

    @mcp.tool(name="searchSessionAutolog")
    async def search_session_autolog(
        query: str,
        limit: int = 15,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        preview_chars: int = 500,
        *,
        ctx: Context,
    ) -> str:
        """Keyword search in SQLite session autolog (separate from Mem0 fact recall)."""
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        limit = max(1, min(limit, 50))
        preview_chars = max(80, min(preview_chars, 1200))
        root = Path((project_root or "").strip() or os.getcwd())
        pid, _ = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        db_path = resolve_db_path(workspace_root=root)
        rows = search_entries(query, project_slug=pid, limit=limit, db_path=db_path)
        header = f"# Session autolog search — `{query}` — project `{pid}` ({len(rows)} hits)\n\n"
        return header + _format_rows(rows, preview_chars=preview_chars)
