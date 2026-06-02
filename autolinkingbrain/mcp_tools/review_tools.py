"""Qwen/Ollama code review MCP tools."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.ollama_client import chat, is_available, review_model
from autolinkingbrain.review_context import (
    build_review_context,
    git_diff,
    review_budget_chars,
)

_REVIEW_SYSTEM = """You are a senior code reviewer. Analyze the provided diff and context.
Output in Russian. Structure:
## Summary
## Findings
For each finding use: severity (critical/major/minor/info), file:line if known, description, suggestion.
Do NOT apply fixes — only review. Skip style nitpicks unless they hide bugs.
"""


def _focus_hint(focus: str) -> str:
    f = (focus or "").strip().lower()
    if f == "security":
        return "Focus on security: injection, auth, secrets, unsafe deserialization."
    if f == "api":
        return "Focus on API contracts, breaking changes, backward compatibility."
    if f == "performance":
        return "Focus on performance: N+1, allocations, hot paths, blocking I/O."
    return ""


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="getReviewBudget")
    async def get_review_budget() -> str:
        """Diagnostic: context char budget for review (32K model ~24K chars default)."""
        b = review_budget_chars()
        return (
            f"model: {review_model()}\n"
            f"total_max_chars: {b['total_max_chars']}\n"
            f"approx_tokens: {b['approx_tokens']}\n"
            f"recommended_diff_chars: {b['recommended_diff_chars']}\n"
            f"ollama_available: {is_available()}"
        )

    @mcp.tool(name="reviewDiff")
    async def review_diff(
        diff: str = "",
        base_ref: str = "",
        head_ref: str = "",
        focus: str = "",
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Code review via local Ollama model (default qwen2.5-coder:7b).

        Pass `diff` directly, or `base_ref` (+ optional `head_ref`) to run git diff in project_root/cwd.
        focus: security | api | performance (optional).
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        project_id, used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        note = mctx.routing_note(project_id, context_path, used_ctx)
        root = Path(project_root or os.getcwd()).resolve()
        if (diff or "").strip():
            patch = diff
        elif base_ref.strip():
            patch = git_diff(root, base_ref=base_ref, head_ref=head_ref)
        else:
            patch = git_diff(root)
        if not patch.strip() or patch.startswith("(git diff failed"):
            return f"Нет diff для review.{note if note else ''}"
        if not is_available():
            return "Ollama недоступен (127.0.0.1:11434). Запустите ollama serve."
        context = build_review_context(mctx, root, patch, project_id=project_id)
        hint = _focus_hint(focus)
        prompt = f"{hint}\n\n{context}" if hint else context
        try:
            review = chat(prompt, system=_REVIEW_SYSTEM)
        except RuntimeError as e:
            return f"Review failed: {e}"
        header = f"# Code Review ({review_model()})\n\n"
        if "CodeGraph index missing" in context:
            header += "_Warning: CodeGraph index missing — impact section limited._\n\n"
        return header + review + note

    @mcp.tool(name="reviewStaged")
    async def review_staged(
        focus: str = "",
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """Review git diff --cached (staged changes) in project cwd."""
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        project_id, used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
        )
        note = mctx.routing_note(project_id, context_path, used_ctx)
        root = Path(project_root or os.getcwd()).resolve()
        patch = git_diff(root, staged=True)
        if not patch.strip() or patch.startswith("(git diff failed"):
            return f"Нет staged изменений для review.{note if note else ''}"
        if not is_available():
            return "Ollama недоступен (127.0.0.1:11434). Запустите ollama serve."
        context = build_review_context(mctx, root, patch, project_id=project_id)
        hint = _focus_hint(focus)
        prompt = f"{hint}\n\n{context}" if hint else context
        try:
            review = chat(prompt, system=_REVIEW_SYSTEM)
        except RuntimeError as e:
            return f"Review failed: {e}"
        return f"# Staged Review ({review_model()})\n\n{review}" + note
