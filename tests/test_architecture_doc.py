"""Tests for architecture_doc."""

from __future__ import annotations

from autolinkingbrain.architecture_doc import default_doc, merge_section, parse_sections, read_doc


def test_parse_and_merge(tmp_path):
    doc = tmp_path / "docs" / "ARCHITECTURE.generated.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(default_doc("backend"), encoding="utf-8")
    merge_section(doc, "modules", "- Auth module uses JWT", project_slug="backend")
    sections = parse_sections(read_doc(doc))
    assert "modules" in sections
    assert "JWT" in sections["modules"].content
    assert sections["modules"].hash.startswith("sha256:")
