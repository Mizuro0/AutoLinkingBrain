"""Session autolog archive in SQLite — separate from Chroma curated memory."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS autolog_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_slug TEXT NOT NULL,
    hook TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    meta_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_autolog_project_created
    ON autolog_entries(project_slug, created_at DESC);
"""


def autolog_backend() -> str:
    """sqlite (default) | mem0 | both — mem0/both require MEM0_AUTOLOG_ALLOW_MEM0=1."""
    raw = os.environ.get("MEM0_AUTOLOG_BACKEND", "sqlite").strip().lower()
    if raw in ("mem0", "legacy"):
        return "mem0"
    if raw == "both":
        return "both"
    return "sqlite"


def mem0_autolog_opt_in() -> bool:
    """Legacy Chroma autolog writes are opt-in so session logs never mix with curated facts."""
    return os.environ.get("MEM0_AUTOLOG_ALLOW_MEM0", "0").strip().lower() in ("1", "true", "yes")


def writes_to_sqlite() -> bool:
    return autolog_backend() in ("sqlite", "both")


def writes_to_mem0() -> bool:
    return mem0_autolog_opt_in() and autolog_backend() in ("mem0", "both")


def resolve_db_path(*, workspace_root: Path | None = None) -> Path:
    custom = os.environ.get("MEM0_AUTOLOG_DB", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    root = workspace_root or Path.cwd()
    return (root / ".cursor" / "autolog.db").resolve()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def append_entry(
    project_slug: str,
    hook: str,
    body: str,
    *,
    meta: dict[str, Any] | None = None,
    db_path: Path | None = None,
    workspace_root: Path | None = None,
) -> int:
    """Append one autolog row; returns row id."""
    path = db_path or resolve_db_path(workspace_root=workspace_root)
    created = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    conn = _connect(path)
    try:
        cur = conn.execute(
            "INSERT INTO autolog_entries(project_slug, hook, body, created_at, meta_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_slug or "unknown", hook, body, created, meta_json),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def list_recent(
    project_slug: str | None = None,
    *,
    limit: int = 50,
    db_path: Path | None = None,
    workspace_root: Path | None = None,
) -> list[dict[str, Any]]:
    path = db_path or resolve_db_path(workspace_root=workspace_root)
    if not path.is_file():
        return []
    limit = max(1, min(limit, 500))
    conn = _connect(path)
    try:
        if project_slug:
            rows = conn.execute(
                "SELECT id, project_slug, hook, body, created_at, meta_json "
                "FROM autolog_entries WHERE project_slug = ? "
                "ORDER BY id DESC LIMIT ?",
                (project_slug, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, project_slug, hook, body, created_at, meta_json "
                "FROM autolog_entries ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for rid, slug, hook, body, created_at, meta_json in rows:
        meta: dict[str, Any] = {}
        if meta_json:
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                meta = {}
        out.append(
            {
                "id": rid,
                "project_slug": slug,
                "hook": hook,
                "body": body,
                "created_at": created_at,
                "meta": meta,
            }
        )
    return out


def list_project_slugs(
    *,
    db_path: Path | None = None,
    workspace_root: Path | None = None,
) -> list[str]:
    path = db_path or resolve_db_path(workspace_root=workspace_root)
    if not path.is_file():
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT project_slug FROM autolog_entries ORDER BY project_slug"
        ).fetchall()
    finally:
        conn.close()
    return [str(r[0]) for r in rows if r[0]]


def search_entries(
    query: str,
    *,
    project_slug: str | None = None,
    limit: int = 20,
    db_path: Path | None = None,
    workspace_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Keyword search in session autolog (SQLite only)."""
    q = (query or "").strip()
    if not q:
        return list_recent(project_slug, limit=limit, db_path=db_path, workspace_root=workspace_root)
    path = db_path or resolve_db_path(workspace_root=workspace_root)
    if not path.is_file():
        return []
    limit = max(1, min(limit, 100))
    like = f"%{q.replace('%', '').replace('_', '')[:200]}%"
    conn = _connect(path)
    try:
        if project_slug:
            rows = conn.execute(
                "SELECT id, project_slug, hook, body, created_at, meta_json "
                "FROM autolog_entries WHERE project_slug = ? AND body LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (project_slug, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, project_slug, hook, body, created_at, meta_json "
                "FROM autolog_entries WHERE body LIKE ? ORDER BY id DESC LIMIT ?",
                (like, limit),
            ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for rid, slug, hook, body, created_at, meta_json in rows:
        meta: dict[str, Any] = {}
        if meta_json:
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                meta = {}
        out.append(
            {
                "id": rid,
                "project_slug": slug,
                "hook": hook,
                "body": body,
                "created_at": created_at,
                "meta": meta,
            }
        )
    return out


def import_from_mem0_row(
    *,
    memory_id: str,
    user_id: str,
    body: str,
    project_slug: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Migrate one Chroma autolog row into SQLite."""
    slug = project_slug or user_id.removeprefix("project_") or user_id
    return append_entry(
        slug,
        "migrate:mem0",
        body,
        meta={"mem0_id": memory_id, "user_id": user_id},
        db_path=db_path,
    )
