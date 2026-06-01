"""Файловое хранилище межзаписных связей для viewer и офлайн-скриптов.

После правок JSON запускайте cross_link_mem0_sync (или suggest с --sync-mem0), чтобы
поле metadata.cross_refs в Mem0 и строки [CROSS_REF_AUTO] в global_topology совпали с файлом.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from autolinkingbrain.paths import REPO_ROOT

DEFAULT_CROSS_LINKS_PATH = REPO_ROOT / "memory_cross_links.json"

RELATIONS = frozenset({"one_to_one", "one_to_many", "many_to_one", "many_to_many"})


def default_document() -> dict:
    return {"version": 1, "edges": []}


def load_cross_links(path: Path | None = None) -> dict:
    p = path or DEFAULT_CROSS_LINKS_PATH
    if not p.exists():
        return default_document()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default_document()
    if not isinstance(data, dict):
        return default_document()
    edges = data.get("edges")
    if not isinstance(edges, list):
        data["edges"] = []
    data.setdefault("version", 1)
    return data


def save_cross_links(data: dict, path: Path | None = None) -> None:
    p = path or DEFAULT_CROSS_LINKS_PATH
    doc = {"version": int(data.get("version", 1)), "edges": list(data.get("edges") or [])}
    for e in doc["edges"]:
        if isinstance(e, dict):
            e.setdefault("source_ids", [])
            e.setdefault("target_ids", [])
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clamp_confidence(x: object) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))


def normalize_edge(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rel = str(raw.get("relation") or "many_to_many").strip()
    if rel not in RELATIONS:
        rel = "many_to_many"
    src = [str(x).strip() for x in (raw.get("source_ids") or raw.get("from_ids") or []) if str(x).strip()]
    tgt = [str(x).strip() for x in (raw.get("target_ids") or raw.get("to_ids") or []) if str(x).strip()]
    if not src or not tgt:
        return None

    aid = raw.get("id")
    if not isinstance(aid, str) or not aid.strip():
        aid = str(uuid.uuid4())

    ben = raw.get("benefits_user_ids") or raw.get("benefits_projects")
    benefits: list[str] = []
    if isinstance(ben, list):
        benefits = [str(x).strip() for x in ben if isinstance(x, (str, int)) and str(x).strip()]

    why = raw.get("rationale_for_agent") or raw.get("why") or raw.get("reason")
    if why is None:
        why_s = ""
    else:
        why_s = str(why).strip()[:8000]

    return {
        "id": aid.strip(),
        "relation": rel,
        "source_ids": src,
        "target_ids": tgt,
        "benefits_user_ids": benefits,
        "rationale_for_agent": why_s,
        "confidence": _clamp_confidence(raw.get("confidence")),
        "source": str(raw.get("source") or "unspecified")[:128],
    }


def fingerprint_edge(e: dict) -> tuple[str, ...]:
    return (
        e.get("relation", ""),
        "|".join(sorted(e.get("source_ids") or [])),
        "|".join(sorted(e.get("target_ids") or [])),
    )


def merge_edges(existing: dict, new_edges: list[dict]) -> tuple[dict, int]:
    """Добавить нормализованные ребра, избегая дубликатов по fingerprint."""

    doc = {"version": int(existing.get("version", 1)), "edges": list(existing.get("edges") or [])}
    cur = doc["edges"]

    seen: set[tuple[str, ...]] = set()
    seen_ids: set[str] = set()
    normalized_existing: list[dict] = []
    for raw in cur:
        if not isinstance(raw, dict):
            continue
        e = normalize_edge(raw)
        if not e:
            continue
        fp = fingerprint_edge(e)
        if fp in seen:
            continue
        seen.add(fp)
        seen_ids.add(e["id"])
        normalized_existing.append(e)

    added = 0
    for raw in new_edges:
        if not isinstance(raw, dict):
            continue
        e = normalize_edge(raw)
        if not e:
            continue
        if e["id"] in seen_ids:
            e["id"] = str(uuid.uuid4())
        fp = fingerprint_edge(e)
        if fp in seen:
            continue
        seen.add(fp)
        seen_ids.add(e["id"])
        normalized_existing.append(e)
        added += 1

    doc["edges"] = normalized_existing
    return doc, added
