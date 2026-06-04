"""Knowledge GC: taxonomy, audit, purge with confirm_token."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from autolinkingbrain.indexing_coverage import is_countable_fact, is_indexing_batch_log
from autolinkingbrain.mem0_lifecycle import is_stale_memory, stale_days_default
from autolinkingbrain.mcp_constants import GLOBAL_ID, INDEXING_MARK_TOKEN, TOPOLOGY_ID

_AUTOLOG_MARKERS = ("[CURSOR]", "[AUT_LOG", "AUT_LOG_LLAMA")
_TRIVIAL_MAX = int(os.environ.get("MEM0_GC_TRIVIAL_MAX_CHARS", "40"))

CATEGORIES = (
    "autolog",
    "indexing_log",
    "stale",
    "duplicate_exact",
    "duplicate_near",
    "wrong_channel",
    "superseded",
    "orphan_topology",
    "empty_or_trivial",
    "keep",
)


@dataclass
class MemoryRow:
    id: str
    user_id: str
    memory: str
    updated_at: str = ""
    created_at: str = ""
    category: str = "keep"

    @classmethod
    def from_dict(cls, row: dict) -> MemoryRow:
        return cls(
            id=str(row.get("id") or ""),
            user_id=str(row.get("user_id") or ""),
            memory=str(row.get("memory") or ""),
            updated_at=str(row.get("updated_at") or ""),
            created_at=str(row.get("created_at") or ""),
        )


@dataclass
class AuditReport:
    user_id: str
    total: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    candidates: list[MemoryRow] = field(default_factory=list)
    confirm_token: str = ""
    generated_at: str = ""

    def purge_ids(self) -> list[str]:
        return [r.id for r in self.candidates if r.category != "keep" and r.id]

    def format_markdown(self) -> str:
        lines = [
            f"# Knowledge audit — `{self.user_id}`",
            f"Generated: {self.generated_at}",
            f"Total rows: {self.total}",
            "",
            "## Counts by category",
        ]
        for cat in CATEGORIES:
            if cat == "keep":
                continue
            n = self.by_category.get(cat, 0)
            if n:
                lines.append(f"- **{cat}**: {n}")
        lines.append(f"- **keep**: {self.by_category.get('keep', 0)}")
        lines.append("")
        lines.append(f"CONFIRM_TOKEN: `{self.confirm_token}`")
        lines.append("(Use with purgeMemories or `brain.py gc purge --confirm-token …`)")
        return "\n".join(lines)


@dataclass
class PurgeResult:
    dry_run: bool
    deleted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class DuplicateGroup:
    fingerprint: str
    ids: list[str]
    preview: str


def _normalize_text(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"\(updated: [^)]+\)", "", t, flags=re.I)
    return t.strip()


def _exact_fingerprint(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode()).hexdigest()[:16]


def classify_row(row: MemoryRow, *, expected_user_id: str, stale_days: int | None = None) -> str:
    body = (row.memory or "").strip()
    if not body or len(body) < 3:
        return "empty_or_trivial"
    if len(body) <= _TRIVIAL_MAX and not body.startswith("["):
        return "empty_or_trivial"
    head = body[:140]
    if any(m in head for m in _AUTOLOG_MARKERS):
        return "autolog"
    if is_indexing_batch_log(body):
        return "indexing_log"
    if row.user_id != expected_user_id and row.user_id not in (GLOBAL_ID, TOPOLOGY_ID):
        return "wrong_channel"
    if row.user_id == TOPOLOGY_ID and expected_user_id != TOPOLOGY_ID:
        if "[LINK]" not in body and "[CROSS_REF" not in body:
            return "orphan_topology"
    if INDEXING_MARK_TOKEN in body and row.user_id.startswith("project_"):
        return "keep"
    if is_stale_memory(
        {"updated_at": row.updated_at, "created_at": row.created_at},
        stale_days=stale_days or stale_days_default(),
    ) and not is_countable_fact(body):
        return "stale"
    if body.startswith("[SUPERSEDED]") or "[superseded by" in body.lower():
        return "superseded"
    return "keep"


def fetch_all_rows(
    db,
    user_id: str,
    *,
    page_size: int = 500,
    max_pages: int = 50,
) -> list[dict]:
    """Paginated get_all — Mem0 may cap rows per call."""
    from autolinkingbrain.mem0_fetch import _fetch_use_sqlite, fetch_channel_rows

    if _fetch_use_sqlite():
        cap = max(1, min(page_size * max_pages, 10000))
        rows = fetch_channel_rows(user_id, top_k=cap, db=db)
        return [
            {**r, "user_id": user_id}
            for r in rows
            if isinstance(r, dict) and r.get("id")
        ]

    all_rows: list[dict] = []
    for page in range(max_pages):
        top_k = page_size * (page + 1)
        raw = db.get_all(filters={"user_id": user_id}, top_k=top_k)
        rows = raw.get("results", []) if isinstance(raw, dict) else raw or []
        if not isinstance(rows, list):
            break
        if len(rows) <= len(all_rows):
            break
        all_rows = [r for r in rows if isinstance(r, dict)]
        if len(rows) < top_k:
            break
    return all_rows


def audit_channel(
    db,
    user_id: str,
    *,
    page: int = 0,
    page_size: int = 500,
    include_duplicates: bool = True,
    stale_days: int | None = None,
) -> AuditReport:
    rows_raw = fetch_all_rows(db, user_id, page_size=page_size)
    parsed = [MemoryRow.from_dict(r) for r in rows_raw if r.get("id")]
    by_cat: dict[str, int] = {c: 0 for c in CATEGORIES}
    candidates: list[MemoryRow] = []
    seen_exact: dict[str, str] = {}

    for row in parsed:
        cat = classify_row(row, expected_user_id=user_id, stale_days=stale_days)
        if include_duplicates and cat == "keep":
            fp = _exact_fingerprint(row.memory)
            if fp in seen_exact and seen_exact[fp] != row.id:
                cat = "duplicate_exact"
            else:
                seen_exact[fp] = row.id
        row.category = cat
        by_cat[cat] = by_cat.get(cat, 0) + 1
        if cat != "keep":
            candidates.append(row)

    start = page * page_size
    page_candidates = candidates[start : start + page_size] if page else candidates

    token_payload = "|".join(sorted(r.id for r in candidates[:200]))
    confirm = hashlib.sha256(
        f"{user_id}:{token_payload}:{secrets.token_hex(8)}".encode()
    ).hexdigest()[:24]

    return AuditReport(
        user_id=user_id,
        total=len(parsed),
        by_category=by_cat,
        candidates=page_candidates if page else candidates,
        confirm_token=confirm,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def verify_confirm_token(report: AuditReport, token: str) -> bool:
    return secrets.compare_digest((token or "").strip(), (report.confirm_token or "").strip())


def purge_candidates(
    db,
    report: AuditReport,
    confirm_token: str,
    *,
    dry_run: bool = True,
    delete_fn: Callable[[str], None] | None = None,
    max_delete: int = 200,
) -> PurgeResult:
    if not verify_confirm_token(report, confirm_token):
        return PurgeResult(dry_run=dry_run, skipped=len(report.purge_ids()), errors=["invalid confirm_token"])
    ids = report.purge_ids()[:max_delete]
    if dry_run:
        return PurgeResult(dry_run=True, deleted=0, skipped=len(ids))
    deleted = 0
    errors: list[str] = []
    from autolinkingbrain.mem0_fetch import _fetch_use_sqlite, delete_memory_sqlite

    for mid in ids:
        try:
            if delete_fn:
                delete_fn(mid)
            elif _fetch_use_sqlite():
                delete_memory_sqlite(mid)
            elif db is not None:
                db.delete(mid)
            else:
                raise RuntimeError("no delete backend (set MEM0_FETCH_SQLITE=1 or pass db)")
            deleted += 1
        except Exception as exc:
            errors.append(f"{mid}: {exc}")
    return PurgeResult(dry_run=False, deleted=deleted, skipped=len(ids) - deleted, errors=errors)


def _purge_log(msg: str, log: Callable[[str], None] | None) -> None:
    if log:
        log(msg)


def _purge_indexing_logs_sqlite(
    *,
    user_id: str | None = None,
    dry_run: bool = True,
    max_delete: int = 5000,
    log: Callable[[str], None] | None = None,
) -> PurgeResult:
    """Direct SQLite purge when chromadb Python client crashes (common on Windows)."""
    from autolinkingbrain.mem0_settings import chroma_path_resolved

    want_uid = (user_id or "").strip() or None
    db_path = chroma_path_resolved() / "chroma.sqlite3"
    if not db_path.is_file():
        return PurgeResult(dry_run=dry_run, errors=[f"missing {db_path}"])

    _purge_log(f"purge-indexing: sqlite {db_path}", log)
    conn = sqlite3.connect(str(db_path), timeout=120)
    try:
        if want_uid:
            rows = conn.execute(
                """
                SELECT DISTINCT d.id
                FROM embedding_metadata d
                INNER JOIN embedding_metadata u ON u.id = d.id AND u.key = 'user_id'
                WHERE d.key = 'data'
                  AND d.string_value LIKE '%Indexed source%'
                  AND u.string_value = ?
                """,
                (want_uid,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT d.id
                FROM embedding_metadata d
                INNER JOIN embedding_metadata u ON u.id = d.id AND u.key = 'user_id'
                WHERE d.key = 'data'
                  AND d.string_value LIKE '%Indexed source%'
                  AND u.string_value LIKE 'project_%'
                """
            ).fetchall()
        ids = [str(r[0]) for r in rows[:max_delete]]
        _purge_log(f"purge-indexing: matched {len(ids)} indexing_log rows", log)
        if dry_run:
            return PurgeResult(dry_run=True, deleted=0, skipped=len(ids))

        deleted = 0
        errors: list[str] = []
        for eid in ids:
            try:
                conn.execute("DELETE FROM embedding_metadata WHERE id = ?", (eid,))
                conn.execute("DELETE FROM embedding_metadata_array WHERE id = ?", (eid,))
                conn.execute("DELETE FROM embeddings WHERE id = ?", (eid,))
                deleted += 1
                if deleted % 200 == 0:
                    conn.commit()
                    _purge_log(f"purge-indexing: deleted {deleted}/{len(ids)}", log)
            except Exception as exc:
                errors.append(f"{eid}: {exc}")
        conn.commit()
        return PurgeResult(
            dry_run=False,
            deleted=deleted,
            skipped=len(ids) - deleted,
            errors=errors,
        )
    finally:
        conn.close()


def purge_indexing_logs_chroma(
    *,
    user_id: str | None = None,
    dry_run: bool = True,
    max_delete: int = 5000,
    log: Callable[[str], None] | None = None,
) -> PurgeResult:
    """Scan Chroma directly and delete Indexed source rows (stable on Windows vs mem0 loop)."""
    import chromadb
    from chromadb.config import Settings

    from autolinkingbrain.mem0_settings import CHROMA_COLLECTION, chroma_path_resolved

    want_uid = (user_id or "").strip() or None
    if os.environ.get("MEM0_PURGE_INDEXING_SQLITE", "1").strip().lower() not in ("0", "false", "no"):
        return _purge_indexing_logs_sqlite(
            user_id=want_uid,
            dry_run=dry_run,
            max_delete=max_delete,
            log=log,
        )

    _purge_log(f"purge-indexing: opening Chroma at {chroma_path_resolved()}", log)
    try:
        client = chromadb.PersistentClient(
            path=str(chroma_path_resolved()),
            settings=Settings(anonymized_telemetry=False),
        )
        col = client.get_collection(CHROMA_COLLECTION)
    except Exception as exc:
        return PurgeResult(dry_run=dry_run, errors=[f"chroma_open: {exc}"])

    ids: list[str] = []
    offset = 0
    batch_size = 500
    scanned = 0
    while len(ids) < max_delete:
        try:
            batch = col.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=offset,
            )
        except Exception as exc:
            return PurgeResult(
                dry_run=dry_run,
                deleted=0,
                skipped=len(ids),
                errors=[f"chroma_get offset={offset}: {exc}"],
            )
        doc_ids = batch.get("ids") or []
        docs = batch.get("documents") or []
        metas = batch.get("metadatas") or []
        if not doc_ids:
            break
        scanned += len(doc_ids)
        if scanned % 2000 == 0 or len(doc_ids) < batch_size:
            _purge_log(f"purge-indexing: scanned {scanned} rows, matched {len(ids)}", log)
        for i, doc_id in enumerate(doc_ids):
            meta = metas[i] if i < len(metas) else {}
            uid = (meta or {}).get("user_id") if isinstance(meta, dict) else ""
            if want_uid and uid != want_uid:
                continue
            if not want_uid and not (isinstance(uid, str) and uid.startswith("project_")):
                continue
            text = docs[i] if i < len(docs) else ""
            if is_indexing_batch_log(str(text or "")):
                ids.append(str(doc_id))
                if len(ids) >= max_delete:
                    break
        if len(doc_ids) < batch_size:
            break
        offset += batch_size

    _purge_log(f"purge-indexing: found {len(ids)} indexing_log rows (cap {max_delete})", log)
    if dry_run:
        return PurgeResult(dry_run=True, deleted=0, skipped=len(ids))

    deleted = 0
    errors: list[str] = []
    chunk = 50
    for start in range(0, len(ids), chunk):
        part = ids[start : start + chunk]
        try:
            col.delete(ids=part)
            deleted += len(part)
            _purge_log(f"purge-indexing: deleted {deleted}/{len(ids)}", log)
        except Exception as exc:
            for mid in part:
                errors.append(f"{mid}: {exc}")
    return PurgeResult(dry_run=False, deleted=deleted, skipped=len(ids) - deleted, errors=errors)


def _purge_indexing_use_subprocess() -> bool:
    v = os.environ.get("MEM0_PURGE_INDEXING_SUBPROCESS", "").strip().lower()
    if v in ("0", "false", "no"):
        return False
    if v in ("1", "true", "yes"):
        return True
    import sys

    return sys.platform == "win32"


def purge_indexing_logs_subprocess(
    *,
    user_id: str | None = None,
    dry_run: bool = True,
    max_delete: int = 5000,
    log: Callable[[str], None] | None = None,
) -> PurgeResult:
    """Run SQLite purge in a child process so an open Mem0/Chroma client in MCP cannot crash."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "_purge_indexing_chroma_sqlite.py"
    if not script.is_file():
        return PurgeResult(dry_run=dry_run, errors=[f"missing worker script: {script}"])

    cmd = [sys.executable, str(script)]
    if not dry_run:
        cmd.append("--apply")
    if user_id:
        cmd.extend(["--user-id", user_id])
    _purge_log(f"purge-indexing: subprocess {' '.join(cmd)}", log)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(120, max_delete // 10),
            cwd=str(script.parents[1]),
        )
    except subprocess.TimeoutExpired:
        return PurgeResult(dry_run=dry_run, errors=["purge-indexing subprocess timed out"])
    except Exception as exc:
        return PurgeResult(dry_run=dry_run, errors=[f"purge-indexing subprocess failed: {exc}"])

    if proc.stderr:
        for line in proc.stderr.splitlines():
            _purge_log(line, log)
    if proc.returncode != 0 and not proc.stdout.strip():
        err = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        return PurgeResult(dry_run=dry_run, errors=[err])

    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return PurgeResult(
            dry_run=dry_run,
            errors=[f"purge-indexing subprocess bad JSON: {exc}; stdout={proc.stdout[:500]!r}"],
        )
    return PurgeResult(
        dry_run=bool(payload.get("dry_run", dry_run)),
        deleted=int(payload.get("deleted", 0)),
        skipped=int(payload.get("skipped", 0)),
        errors=list(payload.get("errors") or []),
    )


def purge_indexing_logs(
    db,
    *,
    user_id: str | None = None,
    dry_run: bool = True,
    max_delete: int = 5000,
    log: Callable[[str], None] | None = None,
) -> PurgeResult:
    """Delete per-file runProjectAnalysis rows (Indexed source `...`) across project channels."""
    use_sqlite = os.environ.get("MEM0_PURGE_INDEXING_SQLITE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if use_sqlite:
        if _purge_indexing_use_subprocess():
            return purge_indexing_logs_subprocess(
                user_id=user_id,
                dry_run=dry_run,
                max_delete=max_delete,
                log=log,
            )
        return _purge_indexing_logs_sqlite(
            user_id=user_id,
            dry_run=dry_run,
            max_delete=max_delete,
            log=log,
        )

    use_chroma = os.environ.get("MEM0_PURGE_INDEXING_CHROMA", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if use_chroma:
        return purge_indexing_logs_chroma(
            user_id=user_id,
            dry_run=dry_run,
            max_delete=max_delete,
            log=log,
        )

    try:
        from autolinkingbrain.mem0_fetch import discover_user_ids
    except Exception as exc:
        return PurgeResult(dry_run=dry_run, errors=[f"discover_user_ids failed: {exc}"])

    uids = [user_id] if user_id else [u for u in discover_user_ids() if u.startswith("project_")]
    ids: list[str] = []
    for uid in uids:
        _purge_log(f"purge-indexing: scanning channel {uid}", log)
        for row in fetch_all_rows(db, uid):
            if not isinstance(row, dict) or not row.get("id"):
                continue
            if is_indexing_batch_log(str(row.get("memory") or "")):
                ids.append(str(row["id"]))
    ids = ids[:max_delete]
    if dry_run:
        return PurgeResult(dry_run=True, deleted=0, skipped=len(ids))
    deleted = 0
    errors: list[str] = []
    for mid in ids:
        try:
            db.delete(mid)
            deleted += 1
        except Exception as exc:
            errors.append(f"{mid}: {exc}")
    return PurgeResult(dry_run=False, deleted=deleted, skipped=len(ids) - deleted, errors=errors)


def list_duplicates(
    db,
    user_id: str,
    *,
    mode: str = "exact",
    page_size: int = 1000,
) -> list[DuplicateGroup]:
    rows_raw = fetch_all_rows(db, user_id, page_size=page_size)
    buckets: dict[str, list[dict]] = {}
    for r in rows_raw:
        if not isinstance(r, dict):
            continue
        text = str(r.get("memory") or "")
        fp = _exact_fingerprint(text)
        buckets.setdefault(fp, []).append(r)
    groups: list[DuplicateGroup] = []
    for fp, items in buckets.items():
        if len(items) < 2:
            continue
        ids = [str(x.get("id") or "") for x in items if x.get("id")]
        preview = (items[0].get("memory") or "")[:90].replace("\n", " ")
        groups.append(DuplicateGroup(fingerprint=fp, ids=ids, preview=preview))
    groups.sort(key=lambda g: -len(g.ids))
    if mode == "near":
        return groups  # near-dedup optional polish — exact for MVP
    return groups
