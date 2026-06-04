"""Tests for fetch_all_memories truncation signaling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autolinkingbrain.mem0_fetch import fetch_all_memories


def test_truncated_when_channel_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "autolinkingbrain.mem0_fetch.discover_user_ids",
        lambda: ["project_test"],
    )
    mem = MagicMock()
    mem.get_all.return_value = {
        "results": [{"id": str(i), "memory": f"fact {i}"} for i in range(500)],
    }
    out = fetch_all_memories(mem=mem, top_k=500)
    assert out["truncated"] is True
    assert "project_test" in out["capped_channels"]
    assert out["limits"]["per_channel_top_k"] == 500


def test_not_truncated_below_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "autolinkingbrain.mem0_fetch.discover_user_ids",
        lambda: ["project_test"],
    )
    mem = MagicMock()
    mem.get_all.return_value = {"results": [{"id": "1", "memory": "one fact"}]}
    out = fetch_all_memories(mem=mem, top_k=500)
    assert out["truncated"] is False
    assert "capped_channels" not in out
