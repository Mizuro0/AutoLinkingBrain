"""SQLite project index state + PROJECT_INDEX.md export."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class EntityRecord:
    path: str
    sha256: str
    code_role: str
    last_seen: str


class ProjectIndexState:
    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.brain_dir = self.project_root / ".brain"
        self.db_path = self.brain_dir / "project_index.db"
        self.md_path = self.brain_dir / "PROJECT_INDEX.md"
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.brain_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        c = self.connect()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS entities (
                path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                code_role TEXT DEFAULT '',
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                entities_processed INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running'
            );
            CREATE TABLE IF NOT EXISTS stale_queue (
                path TEXT PRIMARY KEY,
                reason TEXT,
                queued_at TEXT NOT NULL
            );
            """
        )
        c.commit()

    @staticmethod
    def file_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def upsert_entity(self, path: str, sha256: str, code_role: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        rel = path.replace("\\", "/")
        self.connect().execute(
            "INSERT INTO entities(path, sha256, code_role, last_seen) VALUES(?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256, code_role=excluded.code_role, last_seen=excluded.last_seen",
            (rel, sha256, code_role, now),
        )
        self.connect().commit()

    def get_entity(self, path: str) -> EntityRecord | None:
        rel = path.replace("\\", "/")
        row = self.connect().execute("SELECT * FROM entities WHERE path=?", (rel,)).fetchone()
        if not row:
            return None
        return EntityRecord(path=row["path"], sha256=row["sha256"], code_role=row["code_role"] or "", last_seen=row["last_seen"])

    def list_entities(self) -> list[EntityRecord]:
        rows = self.connect().execute("SELECT * FROM entities ORDER BY path").fetchall()
        return [
            EntityRecord(path=r["path"], sha256=r["sha256"], code_role=r["code_role"] or "", last_seen=r["last_seen"])
            for r in rows
        ]

    def start_run(self, mode: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.connect().execute(
            "INSERT INTO analysis_runs(mode, started_at, status) VALUES(?,?,?)",
            (mode, now, "running"),
        )
        self.connect().commit()
        return int(cur.lastrowid or 0)

    def finish_run(self, run_id: int, *, entities_processed: int, status: str = "ok") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connect().execute(
            "UPDATE analysis_runs SET finished_at=?, entities_processed=?, status=? WHERE id=?",
            (now, entities_processed, status, run_id),
        )
        self.connect().commit()

    def queue_stale(self, path: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connect().execute(
            "INSERT INTO stale_queue(path, reason, queued_at) VALUES(?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET reason=excluded.reason, queued_at=excluded.queued_at",
            (path.replace("\\", "/"), reason, now),
        )
        self.connect().commit()

    def stale_paths(self) -> list[tuple[str, str]]:
        rows = self.connect().execute("SELECT path, reason FROM stale_queue ORDER BY queued_at DESC").fetchall()
        return [(r["path"], r["reason"] or "") for r in rows]

    def export_markdown(self) -> Path:
        entities = self.list_entities()
        stale = self.stale_paths()
        lines = [
            "# Project index (generated)",
            "",
            f"Project root: `{self.project_root}`",
            f"Entities: {len(entities)} | Stale queue: {len(stale)}",
            "",
            "## Entities",
        ]
        for e in entities[:500]:
            lines.append(f"- `{e.path}` role={e.code_role or '-'} sha={e.sha256[:12]}… seen={e.last_seen[:19]}")
        if len(entities) > 500:
            lines.append(f"- … and {len(entities) - 500} more")
        if stale:
            lines.extend(["", "## Stale queue"])
            for p, reason in stale[:100]:
                lines.append(f"- `{p}` — {reason}")
        self.md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self.md_path

    def scan_source_files(
        self,
        *,
        extensions: tuple[str, ...] = (".kt", ".java", ".py", ".ts", ".tsx", ".go"),
        exclude_dirs: tuple[str, ...] = (".git", "node_modules", "build", "dist", ".gradle", "target", "chroma_data"),
        max_files: int = 2000,
    ) -> list[tuple[Path, str]]:
        found: list[tuple[Path, str]] = []
        for path in self.project_root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in exclude_dirs for part in path.parts):
                continue
            if path.suffix.lower() not in extensions:
                continue
            try:
                rel = str(path.relative_to(self.project_root)).replace("\\", "/")
                found.append((path, rel))
            except ValueError:
                continue
            if len(found) >= max_files:
                break
        return found

    def detect_changes(self, files: list[tuple[Path, str]]) -> tuple[list[tuple[Path, str]], list[str]]:
        new_or_changed: list[tuple[Path, str]] = []
        unchanged: list[str] = []
        for path, rel in files:
            try:
                digest = self.file_sha256(path)
            except OSError:
                continue
            prev = self.get_entity(rel)
            if prev is None or prev.sha256 != digest:
                new_or_changed.append((path, rel))
            else:
                unchanged.append(rel)
        return new_or_changed, unchanged
