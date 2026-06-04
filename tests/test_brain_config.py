"""Tests for brain_config."""

from __future__ import annotations

import os
from pathlib import Path

from autolinkingbrain.brain_config import DEFAULTS, _from_merged, _parse_toml_minimal, load_config


def test_parse_toml_minimal():
    text = """
[profile]
name = "minimal"

[mcp]
scope = "project"
"""
    data = _parse_toml_minimal(text)
    assert data["profile"]["name"] == "minimal"
    assert data["mcp"]["scope"] == "project"


def test_from_merged_defaults():
    cfg = _from_merged(DEFAULTS)
    assert cfg.profile == "standard"
    assert cfg.mcp_scope == "global"
    assert cfg.include_qwen is True
    assert cfg.include_arch_curator is False


def test_full_profile_includes_arch():
    data = dict(DEFAULTS)
    data["profile"] = {"name": "full"}
    cfg = _from_merged(data)
    assert cfg.include_arch_curator is True


def test_load_config_no_file(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN_CONFIG_PATH", str(tmp_path / "missing.toml"))
    cfg = load_config()
    assert cfg.profile == "standard"
