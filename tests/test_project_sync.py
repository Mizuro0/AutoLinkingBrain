"""Set-and-forget project sync (index-only, no chromadb in parent)."""

from __future__ import annotations

from pathlib import Path

import pytest

from autolinkingbrain.project_sync import run_index_until_done


def test_run_index_until_done_index_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEM0_FETCH_SQLITE", "1")
    monkeypatch.setenv("MEM0_ANALYSIS_EMIT_SIGNALS", "0")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    out = run_index_until_done(tmp_path, mode="full", batch_size=50, index_only=True)
    assert out.get("ok") is True
    assert (tmp_path / ".brain" / "project_index.db").is_file()
