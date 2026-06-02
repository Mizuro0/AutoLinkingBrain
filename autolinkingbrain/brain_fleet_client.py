"""Fleet client — aggregate local metrics, sanitize, push to hub."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from autolinkingbrain.brain_fleet_sanitize import anonymous_ref, sanitize_payload
from autolinkingbrain.brain_metrics import aggregate


def _install_seed() -> str:
    return os.environ.get("BRAIN_FLEET_INSTALL_ID", socket.gethostname())


def build_snapshot(*, project_slug: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    report = aggregate(days=7.0)
    raw: dict[str, Any] = {
        "schema_version": 1,
        "install_ref": anonymous_ref(_install_seed(), prefix="ref"),
        "device_ref": anonymous_ref(socket.gethostname(), prefix="ref"),
        "project_ref": anonymous_ref(project_slug or "unknown", prefix="ref"),
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_count": int(report.get("total_events") or 0),
        "profile": os.environ.get("BRAIN_PROFILE", "standard"),
        "host_kind": os.environ.get("BRAIN_HOST_KIND", "cursor"),
    }
    if extra:
        raw.update(extra)
    return sanitize_payload(raw)


def push_snapshot(*, url: str, token: str, payload: dict[str, Any] | None = None, project_slug: str = "") -> dict[str, Any]:
    body = payload or build_snapshot(project_slug=project_slug)
    req = urllib.request.Request(
        url.rstrip("/") + "/api/fleet/ingest",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "status": resp.status, "body": resp.read().decode("utf-8")[:500]}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": exc.read().decode("utf-8", errors="replace")[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fleet_enabled() -> bool:
    return os.environ.get("BRAIN_FLEET_ENABLED", "0").strip().lower() in ("1", "true", "yes")
