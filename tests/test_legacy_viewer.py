"""Legacy Streamlit viewer — deprecation and optional deps."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def test_viewer_py_marked_deprecated(repo_root: Path) -> None:
    text = (repo_root / "viewer.py").read_text(encoding="utf-8")
    assert "DEPRECATED" in text
    assert "brain.py start" in text


def test_viewer_py_exits_without_streamlit(repo_root: Path, monkeypatch) -> None:
    import builtins
    import importlib.util

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "streamlit":
            raise ImportError("streamlit not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    spec = importlib.util.spec_from_file_location(
        "viewer_legacy_under_test",
        repo_root / "viewer.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    with pytest.raises(SystemExit) as exc:
        spec.loader.exec_module(mod)
    msg = str(exc.value).lower()
    assert "requirements-legacy" in msg or "brain.py start" in msg


def test_streamlit_not_in_core_requirements(repo_root: Path) -> None:
    core = (repo_root / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "streamlit" not in core

    legacy = (repo_root / "requirements-legacy.txt").read_text(encoding="utf-8").lower()
    assert "streamlit" in legacy
