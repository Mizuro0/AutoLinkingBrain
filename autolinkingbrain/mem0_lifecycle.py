"""Memory age / stale helpers for viewer and MCP lifecycle tools."""

from __future__ import annotations

import os
from datetime import datetime, timezone


def stale_days_default() -> int:
    return max(1, int(os.environ.get("MEM0_STALE_DAYS", "90")))


def parse_memory_timestamp(raw: str | None) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def memory_age_days(row: dict) -> float | None:
    ts = parse_memory_timestamp(row.get("updated_at") or row.get("created_at"))
    if ts is None:
        return None
    now = datetime.now(timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def is_stale_memory(row: dict, *, stale_days: int | None = None) -> bool:
    threshold = stale_days if stale_days is not None else stale_days_default()
    age = memory_age_days(row)
    if age is None:
        return False
    return age >= float(threshold)
