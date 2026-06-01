"""
Запись межканальных связей из memory_cross_links.json в Mem0:

1) metadata.cross_refs у каждой затронутой записи — для агента при search/get_all.
2) Строки в global_topology ([CROSS_REF_AUTO] …) для семантического поиска (retrieveChain/search).

topology-строки дедуплицируются через cross_link_topology_state.json (не плодим при повторных sync).

Использование:
  MEM0_TELEMETRY=false python scripts/sync_cross_links_to_mem0.py --apply

Импорт:
  sync_cross_links_from_files(mem)  после правки brain_link_store
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from autolinkingbrain.brain_link_store import (
    default_document,
    load_cross_links,
    normalize_edge,
)
from autolinkingbrain.mem0_kb_log import log_mem0
from autolinkingbrain.mem0_settings import mem0_vector_config
from autolinkingbrain.paths import REPO_ROOT

os.environ.setdefault("MEM0_TELEMETRY", "false")

TOPOLOGY_USER_ID = "global_topology"
TOPOLOGY_STATE_PATH = REPO_ROOT / "cross_link_topology_state.json"


def _load_topology_state() -> set[str]:
    if not TOPOLOGY_STATE_PATH.exists():
        return set()
    try:
        data = json.loads(TOPOLOGY_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    ids = data.get("logged_edge_ids")
    if not isinstance(ids, list):
        return set()
    return {str(x) for x in ids if isinstance(x, str) and x}


def _save_topology_state(ids: set[str]) -> None:
    TOPOLOGY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOPOLOGY_STATE_PATH.write_text(
        json.dumps({"logged_edge_ids": sorted(ids)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_edges(doc: dict) -> list[dict]:
    out: list[dict] = []
    for raw in doc.get("edges") or []:
        if not isinstance(raw, dict):
            continue
        e = normalize_edge(raw)
        if e:
            out.append(e)
    return out


def _peer_refs_for(mid: str, edges: list[dict]) -> list[dict]:
    """Ссылки с точки зрения записи ``mid`` (для поля metadata.cross_refs)."""
    refs: list[dict] = []
    for e in edges:
        src = {str(x) for x in (e.get("source_ids") or [])}
        tgt = {str(x) for x in (e.get("target_ids") or [])}
        if mid not in src and mid not in tgt:
            continue
        peers = tgt if mid in src else src
        role = "source" if mid in src else "target"
        refs.append(
            {
                "edge_id": str(e["id"]),
                "relation": str(e.get("relation") or "many_to_many"),
                "role": role,
                "peer_memory_ids": sorted(peers),
                "benefits_user_ids": list(e.get("benefits_user_ids") or []),
                "rationale_for_agent": str(e.get("rationale_for_agent") or "")[:6000],
                "confidence": float(e.get("confidence") or 0.0),
                "sync_source": "memory_cross_links.json",
            }
        )
    refs.sort(key=lambda x: x["edge_id"])
    return refs


def sync_cross_links_document(
    mem,
    doc: dict | None = None,
    *,
    write_topology: bool = True,
) -> dict:
    """
    :param mem: экземпляр mem0.Memory (уже from_config).
    :param doc: как load_cross_links(); None — прочитать с диска.
    Возвращает счётчики: updated_meta, topology_appended, skipped, errors.
    """
    if doc is None:
        doc = load_cross_links()
    if not isinstance(doc, dict):
        doc = default_document()

    edges = _normalize_edges(doc)
    mids: set[str] = set()
    for e in edges:
        mids.update(str(x) for x in (e.get("source_ids") or []))
        mids.update(str(x) for x in (e.get("target_ids") or []))

    rows_cache: dict[str, dict | None] = {}
    id_to_uid: dict[str, str] = {}
    cache_get_errors = 0
    for mid in sorted(mids):
        try:
            row = mem.get(mid)
        except Exception:
            rows_cache[mid] = None
            cache_get_errors += 1
            continue
        if not row:
            rows_cache[mid] = None
            cache_get_errors += 1
            continue
        rows_cache[mid] = row
        uid = row.get("user_id")
        if uid:
            id_to_uid[mid] = str(uid)

    updated_meta = 0
    errors: list[str] = []
    for mid in sorted(mids):
        row = rows_cache.get(mid)
        if not row:
            errors.append(f"no_memory:{mid}")
            continue
        text = str(row.get("memory") or "")
        base_meta = dict(row.get("metadata") or {})
        user_id = row.get("user_id")
        refs = _peer_refs_for(mid, edges)
        base_meta["cross_refs"] = refs
        merged = {**base_meta}
        if user_id:
            merged["user_id"] = user_id
        try:
            mem.update(mid, text, metadata=merged)
            log_mem0(
                "write",
                "cross_link.sync.cross_refs_metadata",
                memory_id=mid,
                cross_ref_count=len(refs),
                user_id=user_id,
            )
            updated_meta += 1
        except Exception as exc:
            errors.append(f"update:{mid}:{exc}")

    topology_appended = 0
    if write_topology:
        logged = _load_topology_state()
        next_logged = set(logged)
        for e in edges:
            eid = str(e["id"])
            if eid in logged:
                continue
            src = sorted({str(x) for x in (e.get("source_ids") or [])})
            tgt = sorted({str(x) for x in (e.get("target_ids") or [])})
            chans = sorted({id_to_uid.get(x, "?") for x in [*src, *tgt]})

            ration = str(e.get("rationale_for_agent") or "").replace("\n", " ").strip()
            ration = ration[:420] + ("…" if len(str(e.get("rationale_for_agent") or "")) > 420 else "")
            why_en = ration  # сохраняем язык источника; префикс фиксируется для MCP search

            line = (
                f"[CROSS_REF_AUTO] edge={eid} relation={e.get('relation')} "
                f"channels={','.join(chans)} peers_src={len(src)} peers_tgt={len(tgt)} "
                f"confidence={float(e.get('confidence') or 0):.2f}. Agent: {why_en}"
            )
            try:
                from autolinkingbrain.mem0_provenance import stamp_provenance

                line = stamp_provenance(line, "script:crossLinkSync", detail=f"edge={eid}")
                mem.add(line, user_id=TOPOLOGY_USER_ID, infer=False)
                log_mem0(
                    "write",
                    "cross_link.sync.topology_line",
                    user_id=TOPOLOGY_USER_ID,
                    edge_id=eid,
                    line_chars=len(line),
                )
                next_logged.add(eid)
                topology_appended += 1
            except Exception as exc:
                errors.append(f"topology:{eid}:{exc}")
        _save_topology_state(next_logged)

    return {
        "edges": len(edges),
        "memories_targeted": len(mids),
        "updated_meta": updated_meta,
        "topology_appended": topology_appended,
        "get_miss": cache_get_errors,
        "errors": errors[:50],
        "errors_total": len(errors),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Синхронизировать cross_links в Mem0 + global_topology")
    ap.add_argument("--dry-run", action="store_true", help="Только статистика, без записи в Mem0")
    ap.add_argument("--apply", action="store_true", help="Применить к Mem0")
    ap.add_argument("--no-topology", action="store_true", help="Не добавлять строки в global_topology")
    args = ap.parse_args()
    if args.dry_run and args.apply:
        print("Укажите только один из: --dry-run или --apply", file=sys.stderr)
        return 2
    if not args.dry_run and not args.apply:
        print("Нужен --dry-run или --apply", file=sys.stderr)
        return 2

    doc = load_cross_links()
    edges = _normalize_edges(doc)
    mids: set[str] = set()
    for e in edges:
        mids.update(str(x) for x in (e.get("source_ids") or []))
        mids.update(str(x) for x in (e.get("target_ids") or []))

    print(f"Рёбер в файле: {len(edges)} · уникальных memory id: {len(mids)}")
    if args.dry_run:
        print("Dry-run: Mem0 не трогаем.")
        return 0

    from mem0 import Memory  # noqa: WPS433

    with __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        mem = Memory.from_config(config_dict=mem0_vector_config())
    stats = sync_cross_links_document(mem, doc, write_topology=not args.no_topology)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if not stats.get("errors_total") else 1


if __name__ == "__main__":
    raise SystemExit(main())
