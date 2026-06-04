"""SQLite-backed Mem0 fetch (no chromadb client)."""

from __future__ import annotations

import sqlite3

import pytest

from autolinkingbrain.mem0_fetch import discover_user_ids_sqlite, fetch_all_memories


def _seed_chroma_db(db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE embedding_metadata "
        "(id TEXT, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL, bool_value INTEGER)"
    )
    conn.execute(
        "INSERT INTO embedding_metadata VALUES ('e1','data','hello fact',NULL,NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO embedding_metadata VALUES ('e1','user_id','project_demo',NULL,NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO embedding_metadata VALUES ('e1','created_at','2026-01-01T00:00:00+00:00',NULL,NULL,NULL)"
    )
    conn.commit()
    conn.close()


def test_discover_and_fetch_sqlite(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma_dir = tmp_path / "chroma_data"
    chroma_dir.mkdir()
    _seed_chroma_db(chroma_dir / "chroma.sqlite3")
    monkeypatch.setenv("MEM0_FETCH_SQLITE", "1")
    monkeypatch.setattr(
        "autolinkingbrain.mem0_fetch.chroma_path_resolved",
        lambda: chroma_dir,
    )

    assert discover_user_ids_sqlite() == ["project_demo"]
    out = fetch_all_memories(include_cross_links=False)
    assert out.get("fetch_backend") == "sqlite"
    demo = [n for n in out["nodes"] if n["user_id"] == "project_demo" and n["text"] == "hello fact"]
    assert len(demo) == 1
