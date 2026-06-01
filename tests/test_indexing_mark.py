"""Tests for indexing mark detection in checkProjectHealth."""

from __future__ import annotations

from autolinkingbrain.mcp_context import McpContext


def test_indexing_mark_rejects_autolog_bullet() -> None:
    text = (
        "[CURSOR] [AUT_LOG_LLAMA] (Updated: 2026-04-22): conversation=abc\n"
        "---\n- FINAL_INDEXING_MARK\n- INDEXING_STALE_DAYS"
    )
    assert McpContext._is_indexing_mark_memory(text) is False


def test_indexing_mark_accepts_provenance_mark() -> None:
    text = "[SOURCE: mcp:markIndexingComplete] FINAL_INDEXING_MARK (completed_at=2026-06-01T12:00:00): done"
    assert McpContext._is_indexing_mark_memory(text) is True


def test_indexing_mark_accepts_plain_mark() -> None:
    text = "FINAL_INDEXING_MARK (completed_at=2026-06-01T12:00:00): summary"
    assert McpContext._is_indexing_mark_memory(text) is True
