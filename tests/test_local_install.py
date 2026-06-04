"""Local install YAML (gitignored machine profile)."""

from __future__ import annotations

from pathlib import Path

import pytest

from autolinkingbrain.local_install import load_local_install, resolve_profile


def test_load_example_template(tmp_path: Path) -> None:
    p = tmp_path / "install.yaml"
    p.write_text(
        "profile: full\nmcp_scope: global\nsync_mcp_on_agent_sync: true\n",
        encoding="utf-8",
    )
    cfg = load_local_install(path=p)
    assert cfg is not None
    assert cfg.profile == "full"
    assert cfg.sync_mcp_on_agent_sync is True


def test_cli_overrides_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "install.yaml"
    p.write_text("profile: full\n", encoding="utf-8")
    monkeypatch.setenv("BRAIN_LOCAL_INSTALL_YAML", str(p))
    assert resolve_profile("minimal") == "minimal"
    assert resolve_profile(None) == "full"
