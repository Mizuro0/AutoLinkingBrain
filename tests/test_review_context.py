"""Tests for review context builder."""

from __future__ import annotations

from autolinkingbrain.review_context import (
    parse_changed_files,
    review_budget_chars,
    truncate_diff_by_files,
)


def test_parse_changed_files() -> None:
    diff = """diff --git a/src/Main.kt b/src/Main.kt
+++ b/src/Main.kt
@@ -1 +1 @@
"""
    files = parse_changed_files(diff)
    assert "src/Main.kt" in files


def test_truncate_diff_by_files() -> None:
    big = "diff --git a/a.txt b/a.txt\n" + ("+" * 5000)
    out = truncate_diff_by_files(big, 500)
    assert len(out) <= 600


def test_review_budget_defaults() -> None:
    b = review_budget_chars()
    assert b["total_max_chars"] >= 4000
    assert b["recommended_diff_chars"] > 0
