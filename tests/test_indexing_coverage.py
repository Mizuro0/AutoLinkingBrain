"""Tests for indexing coverage metrics and health/mark gate."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from autolinkingbrain.indexing_coverage import (
    IndexingCoverage,
    analyze_indexing_coverage,
    count_outbound_links,
    indexing_strict,
    is_countable_fact,
    parse_scenario_tags,
)
from autolinkingbrain.mcp_context import McpContext


def test_is_countable_fact_excludes_mark_and_autolog() -> None:
    assert is_countable_fact("FINAL_INDEXING_MARK (completed_at=2026-01-01)") is False
    assert is_countable_fact("[CURSOR] [AUT_LOG] summary") is False
    assert is_countable_fact("[LINK] [backend] depends on [crm] via [API]. Contract: x") is False
    assert is_countable_fact("[KOTLIN] [ARCHITECTURE] (Updated: 2026): stack overview") is True


def test_parse_scenario_tags() -> None:
    text = "[KOTLIN] [ARCHITECTURE] (Updated: 2026-06-01): Monolith with modules"
    assert "architecture" in parse_scenario_tags(text)
    text2 = "[SPRING] [API_CONTRACT] (Updated: 2026): REST endpoints"
    tags = parse_scenario_tags(text2)
    assert "api_contract" in tags


def test_count_outbound_links() -> None:
    rows = [
        "[LINK] [backend] depends on [crm] via [API]. Contract: users API",
        "[LINK] [frontend] depends on [backend] via [API]. Contract: auth",
    ]
    assert count_outbound_links(rows, "backend") == 1
    assert count_outbound_links(rows, "frontend") == 1
    assert count_outbound_links(rows, "crm") == 0


def test_analyze_coverage_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEM0_INDEXING_MIN_FACTS", "3")
    monkeypatch.setenv("MEM0_INDEXING_REQUIRED_SCENARIOS", "architecture,api_contract")
    facts = [
        "[KOTLIN] [ARCHITECTURE] (Updated: 2026): overview",
        "[KOTLIN] [BUGFIX] (Updated: 2026): fixed NPE",
    ]
    cov = analyze_indexing_coverage(facts, [], "backend")
    assert cov.fact_count == 2
    assert "architecture" in cov.scenarios_found
    assert not cov.sufficient
    assert any("facts below minimum" in g for g in cov.gaps)
    assert any("api_contract" in g for g in cov.gaps)


def test_coverage_format_block() -> None:
    cov = IndexingCoverage(
        fact_count=10,
        scenarios_found={"architecture", "api_contract"},
        outbound_deps=2,
        min_facts=8,
        required_scenarios=frozenset({"architecture", "api_contract"}),
        min_outbound_deps=0,
    )
    block = cov.format_block()
    assert "FACTS: 10" in block
    assert "COVERAGE_STATUS: sufficient" in block


def test_health_body_includes_coverage_block() -> None:
    db = MagicMock()
    db.get_all.return_value = {
        "results": [
            {
                "memory": "FINAL_INDEXING_MARK (completed_at=2026-06-01T10:00:00)",
                "created_at": "2026-06-01T10:00:00",
            },
            {
                "memory": "[KOTLIN] [ARCHITECTURE] (Updated: 2026): stack",
                "created_at": "2026-06-01T09:00:00",
            },
        ]
    }
    mctx = McpContext(db=db)
    with patch.object(mctx, "mem_search", return_value=[]):
        with patch(
            "autolinkingbrain.mcp_context.load_topology_memory_texts",
            return_value=[],
        ):
            body = mctx.build_check_project_health_body("backend", "project_backend")
    assert "=== INDEXING COVERAGE ===" in body
    assert "COVERAGE_STATUS:" in body


def test_indexing_strict_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEM0_INDEXING_STRICT", raising=False)
    assert indexing_strict() is True
    monkeypatch.setenv("MEM0_INDEXING_STRICT", "0")
    assert indexing_strict() is False
