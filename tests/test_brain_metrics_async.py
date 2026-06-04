"""Tests for async metrics queue."""

from __future__ import annotations

import time

from autolinkingbrain import brain_metrics_async


def test_enqueue_does_not_raise(monkeypatch):
    monkeypatch.setenv("MEM0_METRICS", "1")
    monkeypatch.setenv("MEM0_METRICS_ASYNC", "1")
    brain_metrics_async.shutdown()
    for i in range(5):
        brain_metrics_async.enqueue_event("test.event", "test", n=i)
    time.sleep(0.2)
    brain_metrics_async.shutdown()
