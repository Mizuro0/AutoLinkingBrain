"""Load all Mem0 memories across channels — shared by Brain Viewer and offline scripts."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, TYPE_CHECKING

_log = logging.getLogger(__name__)

from autolinkingbrain.brain_link_store import load_cross_links
from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0
from autolinkingbrain.mem0_lifecycle import is_stale_memory, stale_days_default
from autolinkingbrain.mem0_settings import CHROMA_COLLECTION, chroma_path_resolved, mem0_vector_config

if TYPE_CHECKING:
    from mem0 import Memory

_META_SKIP = frozenset(
    {"data", "user_id", "created_at", "updated_at", "text_lemmatized"},
)

_mem: Memory | None = None


def _fetch_use_sqlite() -> bool:
    """Direct Chroma SQLite reads (avoids chromadb native crashes on Windows)."""
    return os.environ.get("MEM0_FETCH_SQLITE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _chroma_sqlite_file() -> Path:
    return chroma_path_resolved() / "chroma.sqlite3"


def get_memory() -> Memory:
    """Lazy Mem0 client (avoids Ollama/Chroma init until first use)."""
    from mem0 import Memory

    global _mem
    if _mem is None:
        _mem = Memory.from_config(config_dict=mem0_vector_config())
    return _mem


from autolinkingbrain.mem0_channels import classify_scope  # noqa: E402 — re-export


def discover_user_ids_sqlite() -> list[str]:
    """All unique user_id values from Chroma SQLite (no Python chromadb client)."""
    from autolinkingbrain.mem0_channels import classify_scope

    db_path = _chroma_sqlite_file()
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT string_value
            FROM embedding_metadata
            WHERE key = 'user_id' AND string_value IS NOT NULL AND string_value != ''
            """
        ).fetchall()
    finally:
        conn.close()
    seen = {str(r[0]) for r in rows}

    def _sort_key(uid: str) -> tuple[int, str]:
        scope = classify_scope(uid)
        order = {"global": 0, "topology": 1, "project": 2, "other": 3}
        return order.get(scope, 9), uid

    return sorted(seen, key=_sort_key)


def discover_user_ids() -> list[str]:
    """All unique user_id values from Chroma metadata."""
    if _fetch_use_sqlite():
        return discover_user_ids_sqlite()
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(chroma_path_resolved()),
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_collection(CHROMA_COLLECTION)

    seen: set[str] = set()
    offset = 0
    batch_size = 2000
    while True:
        batch = col.get(include=["metadatas"], limit=batch_size, offset=offset)
        metas = batch.get("metadatas") or []
        if not metas:
            break
        for meta in metas:
            uid = (meta or {}).get("user_id")
            if isinstance(uid, str) and uid:
                seen.add(uid)
        if len(metas) < batch_size:
            break
        offset += batch_size

    def _sort_key(uid: str) -> tuple[int, str]:
        scope = classify_scope(uid)
        order = {"global": 0, "topology": 1, "project": 2, "other": 3}
        return order.get(scope, 9), uid

    return sorted(seen, key=_sort_key)


def _meta_value(row: tuple) -> Any:
    _key, sv, iv, fv, bv = row
    if sv is not None:
        return sv
    if iv is not None:
        return iv
    if fv is not None:
        return fv
    if bv is not None:
        return bool(bv)
    return None


def _load_extra_metadata(conn: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    chunk = 400
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        placeholders = ",".join("?" * len(part))
        rows = conn.execute(
            f"""
            SELECT id, key, string_value, int_value, float_value, bool_value
            FROM embedding_metadata
            WHERE id IN ({placeholders})
              AND key NOT IN ('data','user_id','created_at','updated_at','text_lemmatized')
            """,
            part,
        ).fetchall()
        for eid, key, sv, iv, fv, bv in rows:
            if key in _META_SKIP:
                continue
            out.setdefault(str(eid), {})[str(key)] = _meta_value((key, sv, iv, fv, bv))
    return out


def fetch_scope_ids_sqlite(user_id: str, *, top_k: int) -> list[str]:
    db_path = _chroma_sqlite_file()
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        rows = conn.execute(
            """
            SELECT d.id
            FROM embedding_metadata d
            INNER JOIN embedding_metadata u ON u.id = d.id AND u.key = 'user_id'
            WHERE d.key = 'data' AND u.string_value = ?
            LIMIT ?
            """,
            (user_id, top_k),
        ).fetchall()
        return [str(r[0]) for r in rows]
    finally:
        conn.close()


def delete_scope_sqlite(user_id: str, *, top_k: int) -> tuple[int, list[dict[str, str]]]:
    """Delete up to top_k memories in a channel via SQLite."""
    ids = fetch_scope_ids_sqlite(user_id, top_k=top_k)
    deleted = 0
    failed: list[dict[str, str]] = []
    for mid in ids:
        try:
            delete_memory_sqlite(mid)
            deleted += 1
        except Exception as exc:
            failed.append({"id": mid, "error": str(exc)})
    return deleted, failed


def fetch_channel_rows_sqlite(user_id: str, *, top_k: int = 1000) -> list[dict[str, Any]]:
    """Mem0-shaped rows for one channel (no chromadb Python client)."""
    uid = (user_id or "").strip()
    if not uid:
        return []
    db_path = _chroma_sqlite_file()
    if not db_path.is_file():
        return []
    cap = max(1, min(int(top_k), 10000))
    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        rows = conn.execute(
            """
            SELECT d.id,
                   d.string_value,
                   c.string_value,
                   upd.string_value
            FROM embedding_metadata d
            INNER JOIN embedding_metadata u ON u.id = d.id AND u.key = 'user_id'
            LEFT JOIN embedding_metadata c ON c.id = d.id AND c.key = 'created_at'
            LEFT JOIN embedding_metadata upd ON upd.id = d.id AND upd.key = 'updated_at'
            WHERE d.key = 'data'
              AND d.string_value IS NOT NULL
              AND u.string_value = ?
            ORDER BY COALESCE(upd.string_value, c.string_value, '') DESC
            LIMIT ?
            """,
            (uid, cap),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": str(eid),
            "memory": str(memory or ""),
            "created_at": created_at or "",
            "updated_at": updated_at or "",
            "metadata": {},
        }
        for eid, memory, created_at, updated_at in rows
    ]


def chroma_total_memories_sqlite() -> dict[str, Any]:
    """Collection stats without chromadb Python client (Windows-safe)."""
    db_path = _chroma_sqlite_file()
    if not db_path.is_file():
        return {
            "collection": CHROMA_COLLECTION,
            "total_memories": 0,
            "channels": 0,
            "backend": "sqlite",
            "error": f"missing {db_path}",
        }
    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        total = conn.execute(
            """
            SELECT COUNT(DISTINCT d.id)
            FROM embedding_metadata d
            WHERE d.key = 'data' AND d.string_value IS NOT NULL
            """
        ).fetchone()[0]
        channels = conn.execute(
            """
            SELECT COUNT(DISTINCT string_value)
            FROM embedding_metadata
            WHERE key = 'user_id'
              AND string_value IS NOT NULL
              AND string_value != ''
            """
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "collection": CHROMA_COLLECTION,
        "total_memories": int(total or 0),
        "channels": int(channels or 0),
        "backend": "sqlite",
    }


def fetch_channel_rows(
    user_id: str,
    *,
    top_k: int = 1000,
    db: Any = None,
) -> list[dict[str, Any]]:
    """Load channel memories; uses SQLite when MEM0_FETCH_SQLITE=1 (default)."""
    if _fetch_use_sqlite():
        return fetch_channel_rows_sqlite(user_id, top_k=top_k)
    if db is None:
        db = get_memory()
    try:
        raw = db.get_all(filters={"user_id": user_id}, top_k=top_k)
    except Exception as exc:
        _log.warning("fetch_channel_rows failed for %s: %s", user_id, exc)
        return []
    rows = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def delete_memory_sqlite(memory_id: str) -> None:
    """Delete one embedding row via SQLite (safe when chromadb client crashes)."""
    db_path = _chroma_sqlite_file()
    if not db_path.is_file():
        raise FileNotFoundError(f"missing {db_path}")
    mid = str(memory_id).strip()
    if not mid:
        raise ValueError("empty id")
    conn = sqlite3.connect(str(db_path), timeout=120)
    try:
        for table in ("embedding_metadata", "embedding_metadata_array", "embeddings"):
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (mid,))
        conn.commit()
    finally:
        conn.close()


def fetch_all_memories_sqlite(
    *,
    top_k: int,
    include_cross_links: bool = True,
    log_source: str = "mem.fetch.sqlite",
) -> dict[str, Any]:
    """Viewer-safe fetch without mem0/chromadb Python client."""
    db_path = _chroma_sqlite_file()
    if not db_path.is_file():
        return {
            "error": f"chroma_sqlite_missing: {db_path}",
            "nodes": [],
            "groups": {},
            "truncated": False,
        }

    conn = sqlite3.connect(str(db_path), timeout=120)
    try:
        rows = conn.execute(
            """
            SELECT d.id,
                   d.string_value,
                   u.string_value,
                   c.string_value,
                   upd.string_value
            FROM embedding_metadata d
            INNER JOIN embedding_metadata u ON u.id = d.id AND u.key = 'user_id'
            LEFT JOIN embedding_metadata c ON c.id = d.id AND c.key = 'created_at'
            LEFT JOIN embedding_metadata upd ON upd.id = d.id AND upd.key = 'updated_at'
            WHERE d.key = 'data' AND d.string_value IS NOT NULL
            """
        ).fetchall()
        by_uid: dict[str, list[tuple]] = {}
        for row in rows:
            eid, memory, uid, created_at, updated_at = row
            uid = str(uid or "")
            if not uid:
                continue
            by_uid.setdefault(uid, []).append(
                (str(eid), str(memory or ""), created_at or "", updated_at or ""),
            )

        def _sort_key(uid: str) -> tuple[int, str]:
            scope = classify_scope(uid)
            order = {"global": 0, "topology": 1, "project": 2, "other": 3}
            return order.get(scope, 9), uid

        user_ids = sorted(by_uid.keys(), key=_sort_key)
        nodes: list[dict] = []
        groups: dict[str, int] = {}
        capped_channels: list[str] = []
        selected_ids: list[str] = []

        for uid in user_ids:
            channel_rows = by_uid.get(uid, [])
            channel_rows.sort(key=lambda r: (r[3] or r[2] or ""), reverse=True)
            if len(channel_rows) >= top_k:
                capped_channels.append(uid)
            groups[uid] = len(channel_rows)
            for eid, memory, created_at, updated_at in channel_rows[:top_k]:
                selected_ids.append(eid)
                nodes.append(
                    {
                        "id": eid,
                        "text": memory,
                        "user_id": uid,
                        "scope": classify_scope(uid),
                        "metadata": {},
                        "updated_at": updated_at,
                        "created_at": created_at,
                    }
                )

        if os.environ.get("MEM0_FETCH_SQLITE_META", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            extra = _load_extra_metadata(conn, selected_ids)
        else:
            extra = {}
        for node in nodes:
            node["metadata"] = extra.get(node["id"], {})
            node["stale"] = is_stale_memory(
                {"updated_at": node["updated_at"], "created_at": node["created_at"]},
            )
    finally:
        conn.close()

    log_mem0("read", log_source, top_k=top_k, rows=len(nodes), channels=len(user_ids))

    out: dict[str, Any] = {
        "nodes": nodes,
        "groups": groups,
        "stale_days": stale_days_default(),
        "truncated": bool(capped_channels),
        "limits": {"per_channel_top_k": top_k},
        "fetch_backend": "sqlite",
    }
    if capped_channels:
        out["capped_channels"] = capped_channels
    if include_cross_links:
        cross = load_cross_links()
        if isinstance(cross, dict) and isinstance(cross.get("edges"), list):
            out["cross_links"] = cross
        else:
            out["cross_links"] = {"version": 1, "edges": []}
    return out


def fetch_top_k_default() -> int:
    raw = os.environ.get("MEM0_FETCH_TOP_K", "500").strip()
    try:
        return max(1, min(int(raw), 10000))
    except ValueError:
        return 500


def fetch_all_memories(
    *,
    mem: Memory | None = None,
    log_source: str = "mem.fetch.get_all",
    top_k: int | None = None,
    include_cross_links: bool = True,
) -> dict[str, Any]:
    """
    Flat list of memory nodes + per-channel counts.

    Returns dict with keys: nodes, groups, stale_days, cross_links (optional), error (on failure).
    When any channel hits top_k, truncated=true and capped_channels lists user_ids.
    """
    cap = top_k if top_k is not None else fetch_top_k_default()
    if mem is None and _fetch_use_sqlite():
        return fetch_all_memories_sqlite(
            top_k=cap,
            include_cross_links=include_cross_links,
            log_source=log_source,
        )
    strict = os.environ.get("MEM0_STRICT_ERRORS", "0").strip().lower() in ("1", "true", "yes")
    try:
        user_ids = discover_user_ids()
    except Exception as exc:
        _log.warning("discover_user_ids failed: %s", exc, exc_info=strict)
        return {
            "error": f"chroma_unavailable: {exc}",
            "nodes": [],
            "groups": {},
            "truncated": False,
        }

    nodes: list[dict] = []
    groups: dict[str, int] = {}
    capped_channels: list[str] = []

    try:
        db = mem if mem is not None else get_memory()
    except Exception as exc:
        _log.warning("get_memory failed: %s", exc, exc_info=strict)
        return {
            "error": f"mem0_unavailable: {exc}",
            "nodes": [],
            "groups": {},
            "truncated": False,
        }

    for uid in user_ids:
        try:
            raw = db.get_all(filters={"user_id": uid}, top_k=cap)
            log_mem0(
                "read",
                log_source,
                user_id=uid,
                top_k=cap,
                rows=count_get_all_rows(raw),
            )
            rows = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
        except Exception as exc:
            _log.warning("get_all failed for %s: %s", uid, exc, exc_info=strict)
            rows = []
        if len(rows) >= cap:
            capped_channels.append(uid)
        groups[uid] = len(rows)
        for row in rows:
            meta = row.get("metadata") or {}
            updated_at = row.get("updated_at") or meta.get("updated_at") or ""
            created_at = row.get("created_at") or meta.get("created_at") or ""
            node = {
                "id": str(row.get("id", "")),
                "text": row.get("memory") or "",
                "user_id": uid,
                "scope": classify_scope(uid),
                "metadata": meta,
                "updated_at": updated_at,
                "created_at": created_at,
            }
            node["stale"] = is_stale_memory(
                {"updated_at": updated_at, "created_at": created_at},
            )
            nodes.append(node)

    out: dict[str, Any] = {
        "nodes": nodes,
        "groups": groups,
        "stale_days": stale_days_default(),
        "truncated": bool(capped_channels),
        "limits": {"per_channel_top_k": cap},
    }
    if capped_channels:
        out["capped_channels"] = capped_channels
    if include_cross_links:
        cross = load_cross_links()
        if isinstance(cross, dict) and isinstance(cross.get("edges"), list):
            out["cross_links"] = cross
        else:
            out["cross_links"] = {"version": 1, "edges": []}
    return out
