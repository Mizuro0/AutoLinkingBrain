"""Tests for mem0_gc taxonomy."""

from __future__ import annotations

from autolinkingbrain.mem0_gc import (
    MemoryRow,
    audit_channel,
    classify_row,
    list_duplicates,
    purge_candidates,
    verify_confirm_token,
)


class FakeDb:
    def __init__(self, rows):
        self._rows = rows
        self.deleted = []

    def get_all(self, filters=None, top_k=1000):
        uid = (filters or {}).get("user_id")
        out = [r for r in self._rows if r.get("user_id") == uid]
        return {"results": out[:top_k]}

    def delete(self, mid):
        self.deleted.append(mid)


def test_classify_autolog():
    row = MemoryRow("1", "project_x", "[CURSOR] session log something long enough here")
    assert classify_row(row, expected_user_id="project_x") == "autolog"


def test_classify_keep_fact():
    row = MemoryRow("2", "project_x", "[KOTLIN] [ARCHITECTURE] (Updated: 2026): Module auth service")
    assert classify_row(row, expected_user_id="project_x") == "keep"


def test_audit_and_purge_dry_run(monkeypatch):
    monkeypatch.setenv("MEM0_FETCH_SQLITE", "0")  # exercise injected db, not on-disk SQLite
    rows = [
        {"id": "a", "user_id": "project_t", "memory": "[CURSOR] autolog x" * 5},
        {"id": "b", "user_id": "project_t", "memory": "[JAVA] [API_CONTRACT] (Updated: x): API v1"},
    ]
    db = FakeDb(rows)
    report = audit_channel(db, "project_t")
    assert report.by_category.get("autolog", 0) >= 1
    assert verify_confirm_token(report, report.confirm_token)
    result = purge_candidates(db, report, report.confirm_token, dry_run=True)
    assert result.dry_run and result.deleted == 0


def test_list_duplicates_exact(monkeypatch):
    monkeypatch.setenv("MEM0_FETCH_SQLITE", "0")  # exercise injected db, not on-disk SQLite
    rows = [
        {"id": "1", "user_id": "project_t", "memory": "same text here for duplicate test"},
        {"id": "2", "user_id": "project_t", "memory": "same text here for duplicate test"},
    ]
    groups = list_duplicates(FakeDb(rows), "project_t")
    assert len(groups) == 1
    assert len(groups[0].ids) == 2
