"""Non-blocking metrics queue — never block MCP hot path."""

from __future__ import annotations

import os
import queue
import threading
from typing import Any

from autolinkingbrain import brain_metrics

_QUEUE: queue.Queue[dict[str, Any] | None] | None = None
_WORKER: threading.Thread | None = None
_MAX = int(os.environ.get("MEM0_METRICS_QUEUE_MAX", "4096"))


def async_enabled() -> bool:
    return os.environ.get("MEM0_METRICS_ASYNC", "1").strip().lower() not in ("0", "false", "no")


def _worker_loop(q: queue.Queue) -> None:
    while True:
        item = q.get()
        if item is None:
            break
        try:
            brain_metrics.log_event(**item)
        except Exception:
            pass
        finally:
            q.task_done()


def _ensure_worker() -> queue.Queue:
    global _QUEUE, _WORKER
    if _QUEUE is not None:
        return _QUEUE
    _QUEUE = queue.Queue(maxsize=_MAX)
    _WORKER = threading.Thread(target=_worker_loop, args=(_QUEUE,), daemon=True, name="brain-metrics")
    _WORKER.start()
    return _QUEUE


def enqueue_event(event: str, source: str, **fields: object) -> None:
    if not brain_metrics.events_enabled():
        return
    if not async_enabled():
        brain_metrics.log_event(event, source, **fields)
        return
    payload: dict[str, Any] = {"event": event, "source": source, **fields}
    try:
        _ensure_worker().put_nowait(payload)
    except queue.Full:
        pass


def enqueue_hook(hook: str, status: str, *, project: str = "", **fields: object) -> None:
    enqueue_event(f"hook.{hook}", f"hook.{hook}", status=status, project=project, **fields)


def shutdown() -> None:
    global _QUEUE, _WORKER
    if _QUEUE is None:
        return
    try:
        _QUEUE.put_nowait(None)
    except queue.Full:
        pass
    if _WORKER and _WORKER.is_alive():
        _WORKER.join(timeout=2.0)
    _QUEUE = None
    _WORKER = None
