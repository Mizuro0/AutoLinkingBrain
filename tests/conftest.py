"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_chroma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not touch the developer's chroma_data/."""
    monkeypatch.setenv("MEM0_CHROMA_PATH", str(tmp_path / "chroma_test"))
    monkeypatch.setenv("MEM0_TELEMETRY", "false")
    monkeypatch.setenv("MEM0_PRIVACY_FILTER", "1")


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
