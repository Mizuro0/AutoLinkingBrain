"""Viewer API auth helper tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_viewer_auth_open_when_token_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIEWER_AUTH_TOKEN", raising=False)
    from viewer_server import viewer_auth_ok

    headers = MagicMock()
    headers.get = lambda k, d="": d
    assert viewer_auth_ok(headers) is True


def test_viewer_auth_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIEWER_AUTH_TOKEN", "secret")
    from viewer_server import viewer_auth_ok

    headers = MagicMock()
    headers.get = lambda k, d="": {"Authorization": "Bearer secret"}.get(k, d)
    assert viewer_auth_ok(headers) is True


def test_viewer_auth_rejects_wrong_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIEWER_AUTH_TOKEN", "secret")
    from viewer_server import viewer_auth_ok

    headers = MagicMock()
    headers.get = lambda k, d="": d
    assert viewer_auth_ok(headers) is False
