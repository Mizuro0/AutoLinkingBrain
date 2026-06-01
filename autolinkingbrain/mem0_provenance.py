"""Provenance tags on Mem0 writes — audit trail for MCP tools and hooks."""

from __future__ import annotations

import os
import re

_SOURCE_PREFIX_RE = re.compile(r"^\[SOURCE:[^\]]+\]\s*", re.IGNORECASE)


def provenance_enabled() -> bool:
    return os.environ.get("MEM0_PROVENANCE", "1").strip().lower() not in ("0", "false", "no")


def stamp_provenance(text: str, source: str, *, detail: str = "") -> str:
    """
    Prefix memory body with [SOURCE: ...] (English, searchable).
    Skips if text already starts with [SOURCE:].
    """
    body = (text or "").strip()
    if not body or not provenance_enabled():
        return text or ""

    if _SOURCE_PREFIX_RE.match(body):
        return text

    src = (source or "unknown").strip()
    extras: list[str] = []
    if detail:
        extras.append(detail.strip())
    suffix = f" {' '.join(extras)}" if extras else ""
    tag = f"[SOURCE: {src}{suffix}]"
    return f"{tag} {body}"
