"""Tests for the client-centric (Cursor agent) ROI model in brain_metrics."""

from __future__ import annotations

import pytest

from autolinkingbrain import brain_metrics


@pytest.fixture
def fixed_constants(monkeypatch):
    """Pin ROI knobs so assertions are deterministic regardless of the env."""
    monkeypatch.setattr(brain_metrics, "_CHARS_PER_TOKEN", 4.0)
    monkeypatch.setattr(brain_metrics, "_REUSE_MULT_LOW", 1.5)
    monkeypatch.setattr(brain_metrics, "_REUSE_MULT_MID", 3.0)
    monkeypatch.setattr(brain_metrics, "_REUSE_MULT_HIGH", 6.0)
    monkeypatch.setattr(brain_metrics, "_AVG_FACT_CHARS", 280.0)
    monkeypatch.setattr(brain_metrics, "_USD_PER_1M_INPUT", 3.0)
    monkeypatch.setattr(brain_metrics, "_USD_PER_1M_OUTPUT", 15.0)


def test_roi_measured_reads_and_store_cost(fixed_constants):
    events = [
        # 4000 injected chars -> 1000 input tokens (real, measured)
        {"event": "mem.read", "source": "mcp.retrieveChain.search", "ret_chars": 4000, "hits": 6},
        # 400 stored chars -> 100 output tokens (storeKnowledge = cloud cost)
        {"event": "mem.write", "source": "mcp.storeKnowledge", "stored_chars": 400},
        # autolog reply copy: NOT a cloud cost, must be excluded from cost
        {"event": "mem.write", "source": "hook.afterResponse", "stored_chars": 8000},
        # viewer reads must never count toward injected context
        {"event": "mem.read", "source": "viewer.api", "ret_chars": 99999},
    ]
    roi = brain_metrics._compute_roi(events)

    assert roi["context_injected_tokens"] == 1000
    assert roi["write_tokens"] == 100
    assert roi["autolog_tokens_free"] == 2000  # 8000 / 4
    assert roi["measured_share"] == 1.0

    # net = injected*(mult-1) - write
    assert roi["net_tokens"]["low"] == int(round(1000 * 0.5 - 100))   # 400
    assert roi["net_tokens"]["mid"] == int(round(1000 * 2.0 - 100))   # 1900
    assert roi["net_tokens"]["high"] == int(round(1000 * 5.0 - 100))  # 4900
    assert roi["tokens_saved_estimate"] == roi["net_tokens"]["mid"]

    # cost_usd = 1000/1e6*3 + 100/1e6*15
    assert roi["cost_usd"] == pytest.approx(0.0045)
    # net_usd mid = (3000 tok input avoided)*3/1e6 - cost
    assert roi["net_usd"]["mid"] == pytest.approx(3000 / 1e6 * 3.0 - 0.0045)


def test_roi_legacy_fallback_uses_row_count(fixed_constants):
    # Legacy event without ret_chars -> estimate from rows * avg_fact_chars.
    events = [
        {"event": "mem.read", "source": "mcp.retrieveChain.search", "hits": 2},
    ]
    roi = brain_metrics._compute_roi(events)
    # 2 * 280 = 560 chars -> 140 tokens
    assert roi["context_injected_tokens"] == 140
    assert roi["measured_share"] == 0.0  # nothing measured, all fallback


def test_roi_empty_is_zero(fixed_constants):
    roi = brain_metrics._compute_roi([])
    assert roi["context_injected_tokens"] == 0
    assert roi["write_tokens"] == 0
    assert roi["net_tokens"]["mid"] == 0
    assert roi["measured_share"] == 1.0


def test_aggregate_includes_roi_block(fixed_constants):
    events = [
        {"event": "mem.read", "source": "hook.sessionStart.get_all", "ret_chars": 2000},
        {"event": "mem.write", "source": "mcp.storeKnowledge", "stored_chars": 200},
    ]
    report = brain_metrics._aggregate_events(events, days=7.0)
    roi = report["roi"]
    assert roi["model"] == "client_cursor_net_v2"
    assert roi["context_injected_tokens"] == 500  # 2000 / 4
    assert "net_usd" in roi and "assumptions" in roi
