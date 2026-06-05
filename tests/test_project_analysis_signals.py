"""Tests for curated analysis signals (no per-file Indexed source logs)."""

from __future__ import annotations

from unittest.mock import MagicMock

from autolinkingbrain.brain_record_composer import compose_file_signal
from autolinkingbrain.project_analysis import run_analysis_batch


def test_compose_file_signal_for_service() -> None:
    hint = "package x\n@Service\nclass ConclusionReportServiceImpl : ConclusionReportService"
    fact = compose_file_signal(
        path="src/main/kotlin/lis/service/ConclusionReportServiceImpl.kt",
        content_hint=hint,
        code_role="SERVICE",
        tech="kotlin",
    )
    assert fact is not None
    assert "ConclusionReportServiceImpl" in fact.body
    assert "Indexed source" not in fact.body


def test_compose_file_signal_skips_infra_without_types() -> None:
    assert compose_file_signal(path="utils/helpers.kt", content_hint="// no types", code_role="INFRA") is None


def test_run_analysis_batch_writes_signals_not_index_logs(tmp_path) -> None:
    src = tmp_path / "src" / "main"
    src.mkdir(parents=True)
    kt = src / "ApiController.kt"
    kt.write_text(
        '@RestController\n@RequestMapping("/api")\nclass ApiController { @GetMapping("/health") fun h() = "ok" }',
        encoding="utf-8",
    )
    stored: list[str] = []

    def _add(text: str, uid: str) -> None:
        stored.append(text)

    db = MagicMock()
    result = run_analysis_batch(
        db,
        project_root=tmp_path,
        project_slug="demo",
        mode="full",
        max_entities=10,
        mem_add=_add,
    )
    assert result["processed"] >= 1
    assert result["stored"] == 0
    assert result["signals_stored"] >= 1
    assert all("Indexed source" not in t for t in stored)
    assert any("ApiController" in t for t in stored)
