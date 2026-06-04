"""GC audit/dedupe via SQLite (no chromadb client)."""

from __future__ import annotations

import sqlite3

import pytest

from autolinkingbrain.mem0_gc import audit_channel, list_duplicates


def _seed_chroma_db(db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE embedding_metadata "
        "(id TEXT, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL, bool_value INTEGER)"
    )
    conn.execute(
        "INSERT INTO embedding_metadata VALUES ('a1','data','[PYTHON] [ARCHITECTURE] fact one',NULL,NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO embedding_metadata VALUES ('a1','user_id','project_demo',NULL,NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO embedding_metadata VALUES ('a2','data','[CURSOR] [AUT_LOG] hook noise',NULL,NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO embedding_metadata VALUES ('a2','user_id','project_demo',NULL,NULL,NULL)"
    )
    conn.commit()
    conn.close()


def test_audit_channel_sqlite(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma_dir = tmp_path / "chroma_data"
    chroma_dir.mkdir()
    _seed_chroma_db(chroma_dir / "chroma.sqlite3")
    monkeypatch.setenv("MEM0_FETCH_SQLITE", "1")
    monkeypatch.setattr(
        "autolinkingbrain.mem0_fetch.chroma_path_resolved",
        lambda: chroma_dir,
    )

    report = audit_channel(None, "project_demo")
    assert report.total == 2
    assert report.by_category.get("autolog", 0) >= 1
    groups = list_duplicates(None, "project_demo")
    assert isinstance(groups, list)
