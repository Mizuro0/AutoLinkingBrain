"""Tests for storeKnowledge infer=False default."""

from __future__ import annotations

import pytest

from autolinkingbrain.mem0_settings import mcp_store_infer_enabled


def test_mcp_store_infer_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEM0_MCP_INFER", raising=False)
    assert mcp_store_infer_enabled() is False


def test_mcp_store_infer_enabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEM0_MCP_INFER", "1")
    assert mcp_store_infer_enabled() is True
