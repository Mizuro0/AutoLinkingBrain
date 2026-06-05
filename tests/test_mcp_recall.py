"""Tests for brain-first recall: facts-only retrieve and exact incoming deps."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autolinkingbrain.indexing_coverage import (
    filter_incoming_dependencies,
    is_autolog_memory,
    is_retrievable_fact,
    retrieve_facts_only_enabled,
)
from autolinkingbrain.mcp_context import McpContext


def test_is_autolog_memory() -> None:
    assert is_autolog_memory("[CURSOR] [AUT_LOG_LLAMA] session summary")
    assert not is_retrievable_fact("[CURSOR] [AUT_LOG_LLAMA] session summary")
    assert is_retrievable_fact(
        "[PYTHON] [ARCHITECTURE] (Updated: 2026): brain_server.py bootstraps MCP tools."
    )


def test_filter_incoming_dependencies_exact_slug() -> None:
    rows = [
        "[LINK] [demo-booking] depends on [mcp_server] via [API]. Contract: memory read.",
        "[LINK] [user] depends on [orthanc] via [API]. Contract: DICOM.",
        "[LINK] [gemini_marking] depends on [backend_driven_ui] via [MODULE]. Contract: DTO.",
    ]
    hits = filter_incoming_dependencies(rows, "mcp_server")
    assert len(hits) == 1
    assert "demo-booking" in hits[0]


def test_filter_incoming_case_insensitive() -> None:
    rows = ["[LINK] [x] depends on [MCP_Server] via [API]. Contract: y."]
    assert len(filter_incoming_dependencies(rows, "mcp_server")) == 1


def test_retrieve_chain_excludes_autolog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_RETRIEVE_FACTS_ONLY", "1")
    assert retrieve_facts_only_enabled() is True

    mctx = McpContext(db=MagicMock())
    autolog = "[CURSOR] [AUT_LOG] long session dump " * 20
    fact = "[PYTHON] [ARCHITECTURE] (Updated: 2026): viewer_server.py serves Brain Viewer API."
    mctx.mem_search = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {"id": "1", "memory": autolog},
            {"id": "2", "memory": fact},
        ]
    )
    body = mctx.retrieve_chain_body("viewer API", project_id="mcp_server", top_k_per_scope=3)
    assert fact in body
    assert autolog not in body
    assert "Excluded" in body or "FROM PROJECT" in body


def test_health_incoming_uses_exact_links_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEM0_FETCH_SQLITE", "0")
    db = MagicMock()

    def _get_all(**kwargs: object) -> dict:
        uid = (kwargs.get("filters") or {}).get("user_id")  # type: ignore[union-attr]
        if uid == "project_mcp_server":
            return {
                "results": [
                    {
                        "memory": "FINAL_INDEXING_MARK (completed_at=2026-06-01T10:00:00)",
                        "created_at": "2026-06-01T10:00:00",
                    },
                ]
            }
        if uid == "global_topology":
            return {
                "results": [
                    {"memory": "[LINK] [user] depends on [orthanc] via [API]. Contract: x"},
                    {"memory": "[LINK] [demo] depends on [mcp_server] via [API]. Contract: y"},
                ]
            }
        return {"results": []}

    db.get_all.side_effect = _get_all
    mctx = McpContext(db=db)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            mctx,
            "_analysis_status_block",
            lambda *_a, **_k: "STATUS: ok\nREASON: test\nENTITIES: 0 | STALE_QUEUE: 0\nAUTO_RUN: no",
        )
        body = mctx.build_check_project_health_body("mcp_server", "project_mcp_server")
    assert "orthanc" not in body
    assert "demo" in body
