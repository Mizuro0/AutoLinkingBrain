"""Import smoke — no Ollama/Chroma required for these modules."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_repo_root_on_path(repo_root: Path) -> None:
    assert str(repo_root) in sys.path or Path.cwd() == repo_root


def test_core_package_imports() -> None:
    modules = [
        "autolinkingbrain.paths",
        "autolinkingbrain.mem0_settings",
        "autolinkingbrain.mem0_project_slug",
        "autolinkingbrain.mem0_privacy",
        "autolinkingbrain.mem0_hybrid_search",
        "autolinkingbrain.brain_link_store",
        "autolinkingbrain.mem0_fetch",
        "autolinkingbrain.mem0_kb_log",
    ]
    for name in modules:
        mod = importlib.import_module(name)
        assert mod is not None


def test_entry_points_import_without_side_effects() -> None:
    import brain  # noqa: F401

    assert hasattr(brain, "main")


def test_viewer_server_imports() -> None:
    import viewer_server  # noqa: F401

    assert hasattr(viewer_server, "main")
