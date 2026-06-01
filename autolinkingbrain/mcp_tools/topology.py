"""Topology tools: cross-repo dependency registration."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_constants import ALLOWED_LINK_TYPES, TOPOLOGY_ID
from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.mem0_kb_log import log_mem0


def _link_line(source_project: str, target_project: str, link_type: str, reason: str) -> str:
    return (
        f"[LINK] [{source_project}] depends on [{target_project}] via [{link_type.upper()}]. "
        f"Contract: {reason}"
    )


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="registerDependency")
    async def register_dependency(
        target_project: str,
        link_type: str,
        reason: str,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Регистрирует связь между проектами.

        target_project: Имя проекта или сервиса, от которого мы зависим.
        link_type: Тип связи: 'module' (через Gradle) или 'api' (REST, gRPC, GraphQL).
        reason: Краткое описание контракта (какие данные гоняем или какие методы вызываем).
        context_path: Путь к файлу/директории, над которым работает агент (для monorepo-папок).

        Строка в базе всегда в виде: [LINK] [текущий_проект] depends on [target_project] via [...].
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        target = (target_project or "").strip()
        if not target:
            return "Ошибка: target_project не может быть пустым."

        lt = (link_type or "").strip().lower()
        if lt not in ALLOWED_LINK_TYPES:
            return (
                "Ошибка: link_type должен быть 'module' или 'api' "
                f"(регистр не важен). Получено: {link_type!r}."
            )

        reason_clean = (reason or "").strip()
        if not reason_clean:
            return "Ошибка: reason не может быть пустым."

        rmax = int(os.environ.get("MCP_LINK_REASON_MAX_CHARS", "420"))
        if rmax > 0 and len(reason_clean) > rmax:
            reason_clean = reason_clean[: rmax - 25] + "… [reason truncated]"

        source_project, used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
            infer_from_text=(reason,),
        )
        text = _link_line(source_project, target, lt, reason_clean)

        mctx.mem_add(text, TOPOLOGY_ID, source="mcp:registerDependency", source_detail=f"target={target}")
        log_mem0(
            "write",
            "mcp.registerDependency",
            user_id=TOPOLOGY_ID,
            target_project=target,
            link_type=lt,
            source_project=source_project,
        )
        return (
            f"Связь {source_project} -> {target} ({lt}) зарегистрирована."
            f"{mctx.routing_note(source_project, context_path, used_ctx)}"
        )
