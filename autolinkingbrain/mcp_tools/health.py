"""Health and session bootstrap tools."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.mem0_kb_log import log_mem0


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="checkProjectHealth")
    async def check_project_health(
        max_response_chars: int = 12000,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Проверяет отметку индексации и входящие связи (кто зависит от нас).

        Индексация: подстрока FINAL_INDEXING_MARK в канале project_<slug> (последняя запись по времени).
        Ответ содержит STATUS: и REINDEX_PROTOCOL: (required | not_required) — ориентир для User rules.

        Отметку ставит mark_indexing_complete (не store_knowledge).

        max_response_chars: верхний предел размера ответа (экономия токенов). Переменная окружения
        MCP_HEALTH_MAX_RESPONSE_CHARS переопределяет значение по умолчанию из параметра.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        project_id, _used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        body = mctx.build_check_project_health_body(project_id, f"project_{project_id}")
        cap = int(os.environ.get("MCP_HEALTH_MAX_RESPONSE_CHARS", str(max_response_chars)))
        return mctx.truncate_block(body, max(4000, cap))

    @mcp.tool(name="sessionContextPack")
    async def session_context_pack(
        recall_query: str = "architecture dependencies API stack decisions",
        top_k_per_scope: int = 4,
        max_total_chars: int = 14000,
        check_global: bool = True,
        linked_projects: list[str] | None = None,
        per_memory_chars: int = 850,
        similarity_threshold: float = 0.15,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Один вызов вместо двух: то же, что check_project_health, плюс компактный retrieve_chain по recall_query.

        Меньше round-trip инструментов → меньше накладных расходов; общий потолок max_total_chars.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        project_id, _used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
            infer_from_text=(recall_query,),
        )
        parts = [
            mctx.build_check_project_health_body(project_id, f"project_{project_id}"),
            "\n=== SESSION RECALL ===\n",
            mctx.retrieve_chain_body(
                recall_query,
                project_id=project_id,
                check_global=check_global,
                linked_projects=linked_projects,
                top_k_per_scope=top_k_per_scope,
                per_memory_chars=per_memory_chars,
                threshold=similarity_threshold,
            ),
        ]
        body = "".join(parts)
        log_mem0(
            "read",
            "mcp.sessionContextPack",
            project=project_id,
            recall_preview=(recall_query[:120] + "…") if len(recall_query) > 120 else recall_query,
            max_total_chars=max_total_chars,
        )
        cap = int(os.environ.get("MCP_SESSION_PACK_MAX_CHARS", str(max_total_chars)))
        return mctx.truncate_block(body, max(6000, cap))
