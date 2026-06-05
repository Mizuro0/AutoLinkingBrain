"""Tests for SQLite autolog archive."""

from __future__ import annotations

from pathlib import Path

import pytest

from autolinkingbrain.autolog_store import (
    append_entry,
    autolog_backend,
    list_recent,
    resolve_db_path,
    writes_to_mem0,
    writes_to_sqlite,
)


def test_backend_defaults_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEM0_AUTOLOG_BACKEND", raising=False)
    assert autolog_backend() == "sqlite"
    assert writes_to_sqlite() is True
    assert writes_to_mem0() is False


def test_backend_both_requires_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEM0_AUTOLOG_BACKEND", "both")
    assert writes_to_sqlite() is True
    assert writes_to_mem0() is False
    monkeypatch.setenv("MEM0_AUTOLOG_ALLOW_MEM0", "1")
    assert writes_to_mem0() is True


def test_list_project_slugs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain.autolog_store import list_project_slugs

    db = tmp_path / "autolog.db"
    monkeypatch.setenv("MEM0_AUTOLOG_DB", str(db))
    append_entry("alpha", "hook:test", "one")
    append_entry("beta", "hook:test", "two")
    slugs = list_project_slugs(db_path=db)
    assert slugs == ["alpha", "beta"]


def test_search_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autolinkingbrain.autolog_store import search_entries

    db = tmp_path / "autolog.db"
    monkeypatch.setenv("MEM0_AUTOLOG_DB", str(db))
    append_entry("backend", "hook:test", "Elasticsearch reindex alias swap worked")
    append_entry("backend", "hook:test", "unrelated kotlin dto")
    hits = search_entries("Elasticsearch", project_slug="backend", db_path=db)
    assert len(hits) == 1
    assert "reindex" in hits[0]["body"]


def test_append_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / ".cursor" / "autolog.db"
    monkeypatch.setenv("MEM0_AUTOLOG_DB", str(db))
    rid = append_entry("mcp_server", "hook:test", "[CURSOR] test body", meta={"k": 1})
    assert rid >= 1
    rows = list_recent("mcp_server", limit=10, db_path=db)
    assert len(rows) == 1
    assert rows[0]["hook"] == "hook:test"
    assert "test body" in rows[0]["body"]


def test_resolve_db_path_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = tmp_path / "custom.db"
    monkeypatch.setenv("MEM0_AUTOLOG_DB", str(custom))
    assert resolve_db_path() == custom.resolve()
