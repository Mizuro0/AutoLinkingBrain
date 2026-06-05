"""Tests for project_index_state."""

from __future__ import annotations

from pathlib import Path

from autolinkingbrain.project_index_state import ProjectIndexState


def test_sqlite_upsert_and_export(tmp_path):
    state = ProjectIndexState(tmp_path)
    state.upsert_entity("src/Main.kt", "abc123", "SERVICE")
    rec = state.get_entity("src/Main.kt")
    assert rec is not None
    assert rec.code_role == "SERVICE"
    md = state.export_markdown()
    assert md.is_file()
    text = md.read_text(encoding="utf-8")
    assert "Main.kt" in text
    state.close()


def test_detect_changes(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("v1", encoding="utf-8")
    state = ProjectIndexState(tmp_path)
    files = [(f, "a.py")]
    changed, unchanged = state.detect_changes(files)
    assert len(changed) == 1
    state.upsert_entity("a.py", state.file_sha256(f), "INFRA")
    changed2, _ = state.detect_changes(files)
    assert len(changed2) == 0
    state.close()
