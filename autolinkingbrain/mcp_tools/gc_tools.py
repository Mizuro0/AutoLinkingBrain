"""MCP tools: auditKnowledge, purgeMemories, listDuplicateMemories."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mem0_gc import audit_channel, list_duplicates, purge_candidates
from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.mcp_constants import GLOBAL_ID


# In-process audit cache: token -> report (MVP; single-process MCP)
_AUDIT_CACHE: dict[str, object] = {}


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="auditKnowledge")
    async def audit_knowledge(
        channel: str = "project",
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        include_global: bool = False,
        *,
        ctx: Context,
    ) -> str:
        """
        Dry-run knowledge GC audit for a Mem0 channel. Returns category counts and CONFIRM_TOKEN for purge.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        if channel == "global":
            user_id = GLOBAL_ID
        else:
            pid, _ = mctx.resolve_project(
                project_slug=project_slug,
                project_root=project_root,
                context_path=context_path,
            )
            user_id = f"project_{pid}"
        report = audit_channel(mctx.db, user_id)
        _AUDIT_CACHE[report.confirm_token] = report
        return report.format_markdown()

    @mcp.tool(name="purgeMemories")
    async def purge_memories(
        confirm_token: str,
        dry_run: bool = True,
        *,
        ctx: Context,
    ) -> str:
        """
        Purge GC candidates from prior auditKnowledge. Requires confirm_token. dry_run defaults to True.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        token = (confirm_token or "").strip()
        report = _AUDIT_CACHE.get(token)
        if report is None:
            return "Error: invalid or expired confirm_token — run auditKnowledge first."
        result = purge_candidates(mctx.db, report, token, dry_run=dry_run)
        if not dry_run and token in _AUDIT_CACHE:
            del _AUDIT_CACHE[token]
        return json.dumps(
            {
                "dry_run": result.dry_run,
                "deleted": result.deleted,
                "skipped": result.skipped,
                "errors": result.errors,
            },
            ensure_ascii=False,
        )

    @mcp.tool(name="listDuplicateMemories")
    async def list_duplicate_memories(
        mode: str = "exact",
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """List exact duplicate memory groups in current project channel."""
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        pid, _ = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        groups = list_duplicates(mctx.db, f"project_{pid}", mode=mode)
        lines = [f"Duplicate groups ({mode}): {len(groups)}"]
        for g in groups[:30]:
            lines.append(f"- fp={g.fingerprint} ids={g.ids} preview={g.preview[:80]}")
        return "\n".join(lines)
