"""Defaults for afterAgentResponse autolog hook."""

from __future__ import annotations

from pathlib import Path


def test_autolog_hook_defaults_ollama_off(repo_root: Path) -> None:
    text = (repo_root / ".cursor" / "hooks" / "mem0_autolog_after_response.py").read_text(
        encoding="utf-8",
    )
    assert 'MEM0_AUTOLOG_USE_OLLAMA", "0")' in text
    assert 'in ("1", "true", "yes")' in text
