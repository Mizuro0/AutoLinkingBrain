"""Load all Mem0 memories across channels — shared by Brain Viewer and offline scripts."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from autolinkingbrain.brain_link_store import load_cross_links
from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0
from autolinkingbrain.mem0_lifecycle import is_stale_memory, stale_days_default
from autolinkingbrain.mem0_settings import CHROMA_COLLECTION, chroma_path_resolved, mem0_vector_config

if TYPE_CHECKING:
    from mem0 import Memory

_mem: Memory | None = None


def get_memory() -> Memory:
    """Lazy Mem0 client (avoids Ollama/Chroma init until first use)."""
    from mem0 import Memory

    global _mem
    if _mem is None:
        _mem = Memory.from_config(config_dict=mem0_vector_config())
    return _mem


from autolinkingbrain.mem0_channels import classify_scope  # noqa: E402 — re-export


def discover_user_ids() -> list[str]:
    """All unique user_id values from Chroma metadata."""
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


def fetch_all_memories(
    *,
    mem: Memory | None = None,
    log_source: str = "mem.fetch.get_all",
    top_k: int = 500,
    include_cross_links: bool = True,
) -> dict[str, Any]:
    """
    Flat list of memory nodes + per-channel counts.

    Returns dict with keys: nodes, groups, stale_days, cross_links (optional), error (on failure).
    """
    try:
        user_ids = discover_user_ids()
    except Exception as exc:
        return {
            "error": f"chroma_unavailable: {exc}",
            "nodes": [],
            "groups": {},
        }

    nodes: list[dict] = []
    groups: dict[str, int] = {}

    try:
        db = mem if mem is not None else get_memory()
    except Exception as exc:
        return {"error": f"mem0_unavailable: {exc}", "nodes": [], "groups": {}}

    for uid in user_ids:
        try:
            raw = db.get_all(filters={"user_id": uid}, top_k=top_k)
            log_mem0(
                "read",
                log_source,
                user_id=uid,
                top_k=top_k,
                rows=count_get_all_rows(raw),
            )
            rows = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
        except Exception:
            rows = []
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
    }
    if include_cross_links:
        cross = load_cross_links()
        if isinstance(cross, dict) and isinstance(cross.get("edges"), list):
            out["cross_links"] = cross
        else:
            out["cross_links"] = {"version": 1, "edges": []}
    return out
