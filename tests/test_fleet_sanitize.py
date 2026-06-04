"""Tests for fleet sanitize."""

from __future__ import annotations

from autolinkingbrain.brain_fleet_sanitize import anonymous_ref, sanitize_payload, validate_payload


def test_anonymous_ref_stable():
    assert anonymous_ref("seed") == anonymous_ref("seed")
    assert anonymous_ref("seed").startswith("ref_")


def test_scrub_drops_path_field():
    payload = sanitize_payload({
        "schema_version": 1,
        "install_ref": anonymous_ref("install"),
        "device_ref": anonymous_ref("device"),
        "ts": "2026-06-01T00:00:00Z",
        "health_status": "D:\\codes\\backend\\secret",
    })
    assert "health_status" not in payload


def test_accept_minimal_payload():
    payload = sanitize_payload({
        "schema_version": 1,
        "install_ref": anonymous_ref("install"),
        "device_ref": anonymous_ref("device"),
        "project_ref": anonymous_ref("proj"),
        "ts": "2026-06-01T00:00:00Z",
        "fact_count": 12,
        "analysis_status": "ok",
    })
    assert payload["fact_count"] == 12


def test_scrub_drops_code_snippet_field():
    payload = sanitize_payload({
        "schema_version": 1,
        "install_ref": anonymous_ref("i"),
        "device_ref": anonymous_ref("d"),
        "ts": "2026-06-01T00:00:00Z",
        "health_status": "def foo(): pass",
    })
    assert "health_status" not in payload
