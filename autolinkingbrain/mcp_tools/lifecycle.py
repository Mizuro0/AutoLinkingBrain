"""Memory lifecycle tools: list, stale review, delete."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_constants import GLOBAL_ID
from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0
from autolinkingbrain.mem0_lifecycle import is_stale_memory, stale_days_default


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="listRecentMemories")
    async def list_recent_memories(
        limit: int = 35,
        include_global: bool = False,
        fetch_cap: int = 160,
        preview_chars: int = 90,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Список последних записей Mem0 для ревью жизненного цикла: id, даты, короткий превью-текст.

        Сортировка по updated_at (новые сверху). Не удаляет ничего.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        limit = max(1, min(limit, 100))
        fetch_cap = max(limit, min(fetch_cap, 400))
        preview_chars = max(40, min(preview_chars, 220))
        project_id, _used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        p_user_id = f"project_{project_id}"
        lines: list[str] = []

        def _append_channel(label: str, uid: str) -> None:
            raw = mctx.db.get_all(filters={"user_id": uid}, top_k=fetch_cap)
            log_mem0(
                "read",
                "mcp.listRecentMemories.get_all",
                user_id=uid,
                top_k=fetch_cap,
                rows=count_get_all_rows(raw),
            )
            rows = mctx.rows_sorted_by_time(raw)
            lines.append(f"## {label} (`{uid}`) — showing up to {limit}")
            for row in rows[:limit]:
                mid = str(row.get("id", ""))
                preview = (row.get("memory") or "").replace("\n", " ").strip()[:preview_chars]
                if len((row.get("memory") or "")) > preview_chars:
                    preview += "…"
                ts = row.get("updated_at") or row.get("created_at") or ""
                lines.append(f"• id={mid} | {ts} | {preview}")
            lines.append("")

        _append_channel("Project", p_user_id)
        if include_global:
            _append_channel("Global", GLOBAL_ID)

        body = "\n".join(lines).strip()
        return mctx.truncate_block(
            f"(project slug: {project_id})\n\n{body}",
            int(os.environ.get("MCP_LIST_MEMORIES_MAX_CHARS", "18000")),
        )

    @mcp.tool(name="listStaleMemories")
    async def list_stale_memories(
        stale_days: int = 0,
        limit: int = 40,
        include_global: bool = False,
        fetch_cap: int = 200,
        preview_chars: int = 90,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Записи Mem0 старше порога (MEM0_STALE_DAYS, по умолчанию 90 дней) — для ревью и очистки.

        Сортировка: самые старые сверху. Ничего не удаляет.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        threshold = stale_days if stale_days > 0 else stale_days_default()
        limit = max(1, min(limit, 100))
        fetch_cap = max(limit, min(fetch_cap, 400))
        preview_chars = max(40, min(preview_chars, 220))
        project_id, _used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        p_user_id = f"project_{project_id}"
        lines: list[str] = [f"(stale threshold: {threshold} days, project slug: {project_id})\n"]

        def _append_channel(label: str, uid: str) -> None:
            raw = mctx.db.get_all(filters={"user_id": uid}, top_k=fetch_cap)
            log_mem0(
                "read",
                "mcp.listStaleMemories.get_all",
                user_id=uid,
                top_k=fetch_cap,
                rows=count_get_all_rows(raw),
            )
            rows = mctx.rows_sorted_by_time(raw)
            stale_rows = [r for r in rows if is_stale_memory(r, stale_days=threshold)]
            stale_rows.sort(
                key=lambda r: (r.get("updated_at") or r.get("created_at") or ""),
            )
            lines.append(f"## {label} (`{uid}`) — {len(stale_rows)} stale, showing up to {limit}")
            for row in stale_rows[:limit]:
                mid = str(row.get("id", ""))
                preview = (row.get("memory") or "").replace("\n", " ").strip()[:preview_chars]
                if len((row.get("memory") or "")) > preview_chars:
                    preview += "…"
                ts = row.get("updated_at") or row.get("created_at") or ""
                lines.append(f"• id={mid} | {ts} | {preview}")
            lines.append("")

        _append_channel("Project", p_user_id)
        if include_global:
            _append_channel("Global", GLOBAL_ID)

        body = "\n".join(lines).strip()
        return mctx.truncate_block(
            body,
            int(os.environ.get("MCP_LIST_MEMORIES_MAX_CHARS", "18000")),
        )

    @mcp.tool(name="deleteMemory")
    async def delete_memory(memory_id: str, *, ctx: Context) -> str:
        """
        Удаляет одну запись по id (из viewer или из listRecentMemories).

        Разрешено только для канала project_<slug> и global_skills — не для global_topology.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        mid = (memory_id or "").strip()
        if not mid:
            return "Ошибка: memory_id пустой."

        row = mctx.db.get(mid)
        if not row:
            return f"Не найдено: {mid!r}."

        uid = row.get("user_id")
        if uid not in mctx.allowed_delete_user_ids():
            return (
                f"Отказ: запись в канале {uid!r} — удаление через этот инструмент запрещено "
                "(разрешены только текущий project_* и global_skills)."
            )

        mctx.db.delete(mid)
        log_mem0("write", "mcp.deleteMemory", memory_id=mid, user_id=uid)
        return f"Удалено: {mid} (канал {uid})."
