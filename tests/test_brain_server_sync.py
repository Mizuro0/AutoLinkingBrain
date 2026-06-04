"""brain_server must not sync agent assets on import (MCP hot path)."""

from __future__ import annotations

from pathlib import Path


def test_brain_server_has_no_startup_sync(repo_root: Path) -> None:
    text = (repo_root / "brain_server.py").read_text(encoding="utf-8")
    assert "sync_cursor_agent_assets()" not in text


def test_sync_mcp_startup_respects_env(monkeypatch, tmp_path) -> None:
    from autolinkingbrain import cursor_agent

    monkeypatch.delenv("MEM0_MCP_START_SYNC", raising=False)
    assert cursor_agent.sync_mcp_startup_if_enabled(tmp_path) == []

    monkeypatch.setenv("MEM0_MCP_START_SYNC", "1")
    cursor_agent.SKILLS_SRC_DIR = tmp_path / "config" / "cursor" / "skills"
    cursor_agent.RULES_SRC_DIR = tmp_path / "config" / "cursor" / "rules"
    skill = cursor_agent.SKILLS_SRC_DIR / cursor_agent.SKILL_ID / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: t\n---\n", encoding="utf-8")
    rule = cursor_agent.RULES_SRC_DIR / "autolinking-brain.mdc"
    rule.parent.mkdir(parents=True)
    rule.write_text("---\n---\n", encoding="utf-8")
    monkeypatch.setattr(cursor_agent.Path, "home", lambda: tmp_path)
    ws = tmp_path / "proj"
    ws.mkdir()
    written = cursor_agent.sync_mcp_startup_if_enabled(ws)
    assert written
