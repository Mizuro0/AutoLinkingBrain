"""Tests for agent_hosts."""

from __future__ import annotations

from pathlib import Path

from autolinkingbrain.agent_hosts import resolve_host
from autolinkingbrain.agent_hosts.cursor import CursorHost


def test_cursor_global_mcp_path():
    host = CursorHost()
    p = host.mcp_json_path(scope="global", project_root=None)
    assert p.name == "mcp.json"
    assert ".cursor" in str(p)


def test_cursor_project_mcp_path(tmp_path):
    host = CursorHost()
    p = host.mcp_json_path(scope="project", project_root=tmp_path)
    assert p == tmp_path / ".cursor" / "mcp.json"


def test_resolve_host_auto():
    h = resolve_host("auto")
    assert h.name == "cursor"
