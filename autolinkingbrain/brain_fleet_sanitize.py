"""Sanitize telemetry payloads — zero code/paths/PII on wire."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|/)[^\s\"']{2,}")
_CODE_RE = re.compile(r"(?:def |class |function |import |package |SELECT |INSERT )", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MAX_STR = 64

ALLOWED_TOP_KEYS = frozenset({
    "schema_version",
    "install_ref",
    "device_ref",
    "project_ref",
    "ts",
    "health_status",
    "coverage_status",
    "analysis_status",
    "fact_count",
    "entity_count",
    "event_count",
    "profile",
    "host_kind",
})


def anonymous_ref(seed: str, *, prefix: str = "ref") -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()[:12]
    return f"{prefix}_{h}"


def _scrub_string(val: str) -> str | None:
    s = (val or "").strip()
    if not s:
        return None
    if len(s) > _MAX_STR:
        return None
    if _PATH_RE.search(s):
        return None
    if _CODE_RE.search(s):
        return None
    if _EMAIL_RE.search(s):
        return None
    if "memory" in s.lower() and len(s) > 20:
        return None
    return s


def sanitize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"schema_version": 1}
    for key in ALLOWED_TOP_KEYS:
        if key not in raw:
            continue
        val = raw[key]
        if isinstance(val, bool):
            out[key] = val
        elif isinstance(val, int):
            out[key] = max(0, min(val, 10_000_000))
        elif isinstance(val, str):
            cleaned = _scrub_string(val)
            if cleaned is not None:
                out[key] = cleaned
        elif key == "schema_version" and isinstance(val, int):
            out[key] = val
    if len(out) < 2:
        raise ValueError("payload empty after sanitization")
    return out


def validate_payload(raw: dict[str, Any]) -> tuple[bool, str]:
    try:
        sanitize_payload(raw)
        return True, "ok"
    except ValueError as exc:
        return False, str(exc)
