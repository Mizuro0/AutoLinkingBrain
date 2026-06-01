"""Redact secrets before any Mem0 write (MCP tools and Cursor hooks)."""

from __future__ import annotations

import os
import re

# Ordered: more specific first where it matters.
_REDACT_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
            re.MULTILINE,
        ),
        "[PRIVATE KEY REDACTED]",
    ),
    (
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "[JWT REDACTED]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "sk-[REDACTED]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"), "ghp_[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA[REDACTED]"),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(
            r"(?i)(mongodb|postgres(?:ql)?|mysql|redis|amqp|mssql)://[^\s:@/]+:[^\s@/]+@"
        ),
        r"\1://[REDACTED]:[REDACTED]@",
    ),
    (
        re.compile(
            r"(?i)(api[_-]?key|secret|password|passwd|pwd|token|authorization|"
            r"client[_-]?secret|access[_-]?token|refresh[_-]?token|private[_-]?key)"
            r"\s*[:=]\s*\S+"
        ),
        r"\1=[REDACTED]",
    ),
]


def privacy_filter_enabled() -> bool:
    return os.environ.get("MEM0_PRIVACY_FILTER", "1").strip().lower() not in ("0", "false", "no")


def redact_secrets(text: str) -> str:
    """Return text with common secret patterns replaced."""
    if not text or not privacy_filter_enabled():
        return text
    out = text
    for pattern, repl in _REDACT_RULES:
        out = pattern.sub(repl, out)
    return out


def prepare_for_storage(text: str) -> tuple[str, bool]:
    """Redact secrets; returns (safe_text, was_modified)."""
    if not text:
        return text, False
    safe = redact_secrets(text)
    return safe, safe != text


def should_block_write(text: str) -> bool:
    """
    Optional hard block when text still looks like a raw secret blob.
    MEM0_PRIVACY_BLOCK=1 enables blocking writes that match high-risk patterns only.
    """
    if os.environ.get("MEM0_PRIVACY_BLOCK", "0").strip().lower() not in ("1", "true", "yes"):
        return False
    risky = (
        re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text),
        re.search(r"\bsk-[A-Za-z0-9]{20,}\b", text),
        re.search(r"(?i)password\s*[:=]\s*\S{8,}", text),
    )
    return any(risky)
