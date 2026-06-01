"""Tests for MCP module split and installer env defaults."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_mcp_package_imports() -> None:
    modules = [
        "autolinkingbrain.mcp_constants",
        "autolinkingbrain.mcp_context",
        "autolinkingbrain.mcp_tools",
        "autolinkingbrain.mcp_tools.topology",
        "autolinkingbrain.mcp_tools.health",
        "autolinkingbrain.mcp_tools.knowledge",
        "autolinkingbrain.mcp_tools.lifecycle",
        "autolinkingbrain.mcp_tools.indexing",
    ]
    for name in modules:
        mod = importlib.import_module(name)
        assert mod is not None


def test_mem0_env_helper() -> None:
    from autolinkingbrain.brain_install import _mem0_env

    assert _mem0_env() == {"MEM0_TELEMETRY": "false"}


def test_merge_mcp_includes_telemetry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain.brain_install import _merge_mcp

    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    mcp_path = cursor_dir / "mcp.json"
    monkeypatch.setattr("autolinkingbrain.brain_install.Path.home", lambda: tmp_path)

    py = tmp_path / "python.exe"
    py.write_text("", encoding="utf-8")

    with patch("autolinkingbrain.brain_install.ROOT", tmp_path):
        out = _merge_mcp(py, with_codegraph=False)

    assert out == mcp_path
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["AutoLinkingBrain"]
    assert entry["env"]["MEM0_TELEMETRY"] == "false"


def test_register_tools_wires_all_domains() -> None:
    from autolinkingbrain.mcp_context import McpContext
    from autolinkingbrain.mcp_tools import register_tools

    mcp = MagicMock()
    mctx = McpContext(db=MagicMock())
    register_tools(mcp, mctx)
    assert mcp.tool.call_count == 9
