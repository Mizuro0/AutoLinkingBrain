"""Knowledge GC: taxonomy, audit, purge with confirm_token."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from autolinkingbrain.indexing_coverage import is_countable_fact
from autolinkingbrain.mem0_lifecycle import is_stale_memory, stale_days_default
from autolinkingbrain.mcp_constants import GLOBAL_ID, INDEXING_MARK_TOKEN, TOPOLOGY_ID

_AUTOLOG_MARKERS = ("[CURSOR]", "[AUT_LOG", "AUT_LOG_LLAMA")
_TRIVIAL_MAX = int(os.environ.get("MEM0_GC_TRIVIAL_MAX_CHARS", "40"))

CATEGORIES = (
    "autolog",
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
    for mid in ids:
        try:
            if delete_fn:
                delete_fn(mid)
            else:
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
