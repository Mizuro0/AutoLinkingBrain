"""Ollama module architect protocol (handoff + artifacts)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autolinkingbrain.architecture_protocol import (
    read_handoff,
    record_agent_review,
    run_architect_module,
    start_run,
)


def test_plan_and_run_module_mocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEM0_FETCH_SQLITE", "1")

    def _fake_chat(prompt: str, **kwargs: object) -> str:
        return (
            "## Summary\nBooking API slice.\n\n"
            "## apis\n- POST /bookings\n\n"
            "## open_questions\n"
            "- Q: Which DB owns reservations?\n"
        )

    monkeypatch.setattr("autolinkingbrain.architecture_protocol.chat", _fake_chat)
    monkeypatch.setattr("autolinkingbrain.architecture_protocol.is_available", lambda **_: True)

    start_run(tmp_path, ["online-booking"])
    out = run_architect_module(
        tmp_path,
        module="online-booking",
        context="src/api/booking.py handles HTTP",
        section_focus="apis",
    )
    assert out["ok"] is True
    artifact = tmp_path / out["artifact_path"]
    assert artifact.is_file()
    text = artifact.read_text(encoding="utf-8")
    assert "Booking API" in text
    assert "## agent_review" in text

    handoff = read_handoff(tmp_path)
    assert handoff["signal"] == "module_ready"
    assert handoff["module"] == "online-booking"
    assert len(handoff.get("open_questions") or []) >= 1

    rev = record_agent_review(
        tmp_path,
        module="online-booking",
        agent_status="done",
        agent_notes="Uses PostgreSQL bookings table.",
        resolved_questions=["Q1"],
    )
    assert rev["ok"] is True
    updated = artifact.read_text(encoding="utf-8")
    assert "PostgreSQL" in updated

    run_path = tmp_path / ".brain" / "architecture" / "run.json"
    run_data = json.loads(run_path.read_text(encoding="utf-8"))
    assert "online-booking" in run_data["completed"]
