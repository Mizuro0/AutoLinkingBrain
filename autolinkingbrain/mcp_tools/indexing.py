"""Indexing lifecycle tools."""

from __future__ import annotations

import os
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_constants import INDEXING_MARK_TOKEN
from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.mem0_kb_log import log_mem0


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="markIndexingComplete")
    async def mark_indexing_complete(
        summary: str = "",
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Фиксирует завершение полной индексации текущего проекта (протокол FINAL_INDEXING_MARK).

        В канал project_<slug> добавляется строка, обязательно содержащая подстроку FINAL_INDEXING_MARK
        в начале содержимого памяти — именно её находит check_project_health (через get_all, не search).

        Не вставляйте маркер только внутрь store_knowledge с tech/scenario — для отчёта о индексации
        вызывайте этот инструмент.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        now = datetime.now().isoformat()
        line = f"{INDEXING_MARK_TOKEN} (completed_at={now})"
        smax = int(os.environ.get("MCP_INDEXING_SUMMARY_MAX_CHARS", "900"))
        sm = (summary or "").strip()
        if sm:
            if smax > 0 and len(sm) > smax:
                sm = sm[: smax - 20] + "… [truncated]"
            line += f": {sm}"
        project_id, used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
            infer_from_text=(summary,),
        )
        p_user_id = f"project_{project_id}"
        mctx.mem_add(
            line,
            p_user_id,
            infer=False,
            source="mcp:markIndexingComplete",
            source_detail=f"project={project_id}",
        )
        log_mem0("write", "mcp.markIndexingComplete", user_id=p_user_id, project_id=project_id)
        return f"Отметка индексации сохранена в канале проекта.{mctx.routing_note(project_id, context_path, used_ctx)}"
