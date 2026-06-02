"""Thin Ollama chat client for local code review."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def review_model() -> str:
    return os.environ.get("OLLAMA_REVIEW_MODEL", "qwen2.5-coder:7b").strip() or "qwen2.5-coder:7b"


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def chat(
    prompt: str,
    *,
    system: str = "",
    model: str | None = None,
    temperature: float = 0.2,
    timeout_sec: int | None = None,
) -> str:
    """Send a single-turn chat to Ollama /api/chat and return assistant text."""
    if timeout_sec is None:
        timeout_sec = int(os.environ.get("OLLAMA_REVIEW_TIMEOUT_SEC", "120"))
    payload: dict = {
        "model": model or review_model(),
        "messages": [],
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system.strip():
        payload["messages"].append({"role": "system", "content": system.strip()})
    payload["messages"].append({"role": "user", "content": prompt})
    req = urllib.request.Request(
        f"{ollama_base_url()}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unavailable at {ollama_base_url()}: {e}") from e
    msg = data.get("message") if isinstance(data, dict) else None
    if isinstance(msg, dict):
        return str(msg.get("content") or "").strip()
    return str(data.get("response") or "").strip()


def is_available(*, timeout_sec: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{ollama_base_url()}/api/tags", timeout=timeout_sec) as resp:
            return resp.status == 200
    except Exception:
        return False
