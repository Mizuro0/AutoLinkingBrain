from __future__ import annotations

import os

import pytest

from autolinkingbrain.mem0_privacy import prepare_for_storage, redact_secrets, should_block_write


def test_redact_api_key() -> None:
    raw = "config api_key=supersecret12345 end"
    out = redact_secrets(raw)
    assert "supersecret12345" not in out
    assert "[REDACTED]" in out


def test_redact_sk_openai_style() -> None:
    key = "sk-" + "a" * 24
    out = redact_secrets(f"token {key}")
    assert key not in out
    assert "sk-[REDACTED]" in out


def test_prepare_for_storage_flags_modification() -> None:
    safe, changed = prepare_for_storage("password=abcdefgh1234")
    assert changed is True
    assert "abcdefgh1234" not in safe


def test_should_block_write_only_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("MEM0_PRIVACY_BLOCK", "0")
    assert should_block_write("password=abcdefgh1234") is False

    monkeypatch.setenv("MEM0_PRIVACY_BLOCK", "1")
    assert should_block_write("password=abcdefgh1234") is True
    assert should_block_write("harmless note") is False


def test_privacy_filter_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MEM0_PRIVACY_FILTER", "0")
    secret = "api_key=stillvisible"
    assert redact_secrets(secret) == secret
