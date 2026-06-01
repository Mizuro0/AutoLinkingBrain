from __future__ import annotations

from pathlib import Path

from autolinkingbrain.brain_link_store import (
    default_document,
    load_cross_links,
    merge_edges,
    normalize_edge,
    save_cross_links,
)


def test_normalize_edge_requires_both_sides() -> None:
    assert normalize_edge({"source_ids": ["a"], "target_ids": []}) is None
    assert normalize_edge({"source_ids": ["a"], "target_ids": ["b"], "relation": "one_to_one"}) is not None


def test_normalize_edge_invalid_relation_defaults() -> None:
    e = normalize_edge({"source_ids": ["a"], "target_ids": ["b"], "relation": "invalid"})
    assert e is not None
    assert e["relation"] == "many_to_many"


def test_merge_edges_deduplicates_by_fingerprint() -> None:
    base = default_document()
    edge = {"source_ids": ["mem-1"], "target_ids": ["mem-2"], "relation": "one_to_one"}
    doc, added = merge_edges(base, [edge, edge])
    assert added == 1
    assert len(doc["edges"]) == 1


def test_load_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "links.json"
    doc = default_document()
    doc, _ = merge_edges(doc, [{"source_ids": ["x"], "target_ids": ["y"]}])
    save_cross_links(doc, path)
    loaded = load_cross_links(path)
    assert len(loaded["edges"]) == 1
    assert loaded["edges"][0]["source_ids"] == ["x"]
