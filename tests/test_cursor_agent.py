"""Tests for global Cursor agent skill/rules sync."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_sync_cursor_agent_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain import cursor_agent

    monkeypatch.setattr(cursor_agent, "REPO_ROOT", tmp_path)
    cursor_agent.SOURCE_ROOT = tmp_path / "config" / "cursor"
    cursor_agent.SKILL_SRC = cursor_agent.SOURCE_ROOT / "skills" / cursor_agent.SKILL_ID / "SKILL.md"
    cursor_agent.RULES_SRC_DIR = cursor_agent.SOURCE_ROOT / "rules"

    skill_src = cursor_agent.SKILL_SRC
    skill_src.parent.mkdir(parents=True)
    skill_src.write_text("---\nname: test\n---\n# skill\n", encoding="utf-8")

    rule_src = cursor_agent.RULES_SRC_DIR / "autolinking-brain.mdc"
    rule_src.parent.mkdir(parents=True)
    rule_src.write_text("---\nalwaysApply: false\n---\n# rule\n", encoding="utf-8")

    monkeypatch.setattr(cursor_agent.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("MEM0_SKIP_CURSOR_AGENT_SYNC", raising=False)

    ws = tmp_path / "my-project"
    ws.mkdir()
    written = cursor_agent.sync_cursor_agent_assets(ws, force=True)
    assert len(written) == 2
    assert (tmp_path / ".cursor" / "skills" / cursor_agent.SKILL_ID / "SKILL.md").is_file()
    assert (ws / ".cursor" / "rules" / "autolinking-brain.mdc").is_file()
    assert cursor_agent.agent_assets_configured(ws)


def test_sync_project_rules_for_workspace_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain import cursor_agent

    cursor_agent.RULES_SRC_DIR = tmp_path / "config" / "cursor" / "rules"
    rule_src = cursor_agent.RULES_SRC_DIR / "autolinking-brain.mdc"
    rule_src.parent.mkdir(parents=True)
    rule_src.write_text("---\nalwaysApply: false\n---\n# rule\n", encoding="utf-8")
    monkeypatch.delenv("MEM0_SKIP_CURSOR_AGENT_SYNC", raising=False)

    ws_a = tmp_path / "backend"
    ws_b = tmp_path / "crm"
    ws_a.mkdir()
    ws_b.mkdir()
    written = cursor_agent.sync_project_rules_for_workspace_roots(
        [str(ws_a), str(ws_b)],
        cwd=str(ws_a),
        force=True,
    )
    assert len(written) == 2
    assert (ws_a / ".cursor" / "rules" / "autolinking-brain.mdc").is_file()
    assert (ws_b / ".cursor" / "rules" / "autolinking-brain.mdc").is_file()


def test_eligible_rule_sync_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain import cursor_agent

    monkeypatch.setattr(cursor_agent, "REPO_ROOT", tmp_path)
    server = tmp_path / "mcp_server"
    server.mkdir()
    (server / ".git").mkdir()
    (server / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    nested = server / "scripts"
    nested.mkdir()
    (nested / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    other = tmp_path / "backend"
    other.mkdir()
    (other / ".git").mkdir()

    assert cursor_agent._eligible_rule_sync_root(server)
    assert cursor_agent._eligible_rule_sync_root(other)
    assert not cursor_agent._eligible_rule_sync_root(nested)


def test_sync_skipped_by_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain.cursor_agent import sync_cursor_agent_assets

    monkeypatch.setenv("MEM0_SKIP_CURSOR_AGENT_SYNC", "1")
    assert sync_cursor_agent_assets(tmp_path, force=True) == []


def test_merge_cursor_config_includes_agent_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain import cursor_agent
    from autolinkingbrain.brain_install import merge_cursor_config

    monkeypatch.setattr(cursor_agent, "REPO_ROOT", tmp_path)
    cursor_agent.SOURCE_ROOT = tmp_path / "config" / "cursor"
    cursor_agent.SKILL_SRC = cursor_agent.SOURCE_ROOT / "skills" / cursor_agent.SKILL_ID / "SKILL.md"
    cursor_agent.RULES_SRC_DIR = cursor_agent.SOURCE_ROOT / "rules"
    cursor_agent.SKILL_SRC.parent.mkdir(parents=True)
    cursor_agent.SKILL_SRC.write_text("---\nname: test\n---\n", encoding="utf-8")
    cursor_agent.RULES_SRC_DIR.mkdir(parents=True)
    (cursor_agent.RULES_SRC_DIR / "autolinking-brain.mdc").write_text("---\n---\n", encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("autolinkingbrain.brain_install.ROOT", tmp_path)

    py = tmp_path / "python.exe"
    py.write_text("", encoding="utf-8")

    written = merge_cursor_config(py, with_codegraph=False)
    skill_dest = tmp_path / ".cursor" / "skills" / cursor_agent.SKILL_ID / "SKILL.md"
    rule_dest = tmp_path / ".cursor" / "rules" / "autolinking-brain.mdc"
    assert skill_dest in written
    assert rule_dest in written
    assert skill_dest.is_file()
    assert rule_dest.is_file()
