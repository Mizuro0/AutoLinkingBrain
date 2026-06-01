"""Единый append-лог операций с Mem0/Chroma (чтение и запись)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from autolinkingbrain.paths import REPO_ROOT

_DEFAULT_LOG = REPO_ROOT / ".cursor" / "mem0_kb_activity.log"


def kb_log_path() -> Path:
    return Path(os.environ.get("MEM0_KB_LOG_PATH", str(_DEFAULT_LOG))).expanduser().resolve()


def kb_logging_enabled() -> bool:
    return os.environ.get("MEM0_KB_LOG", "1").strip().lower() not in ("0", "false", "no")


def log_mem0(op: str, source: str, **fields: object) -> None:
    """
    op: 'read' | 'write'
    source: короткий идентификатор вызывающей стороны (mcp.*, hook.*, viewer.*)
    """
    event = "mem.read" if op == "read" else "mem.write" if op == "write" else f"mem.{op}"
    try:
        from autolinkingbrain.brain_metrics import log_event

        log_event(event, source, **fields)
    except Exception:
        pass

    if not kb_logging_enabled():
        return
    path = kb_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "op": op,
            "source": source,
        }
        rec.update(fields)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def normalize_search_results(mem: object) -> list[dict]:
    """Mem0 search возвращает dict с ключом results или (в редких случаях) список."""
    if mem is None:
        return []
    if isinstance(mem, dict):
        return list(mem.get("results") or [])
    if isinstance(mem, list):
        return mem
    return []


def count_get_all_rows(raw: object) -> int:
    if isinstance(raw, dict):
        return len(raw.get("results") or [])
    if isinstance(raw, list):
        return len(raw)
    return 0
