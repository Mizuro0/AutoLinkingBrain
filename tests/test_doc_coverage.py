"""Documentation coverage guards (structure, not prose quality)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Layers that should have a dedicated README (UA doc coverage ~22% before this).
REQUIRED_LAYER_READMES = (
    "README.md",
    "autolinkingbrain/README.md",
    ".cursor/hooks/README.md",
    "viewer_web/README.md",
    "scripts/README.md",
    "docs/ARCHITECTURE.md",
    "docs/CONTRIBUTING.md",
)

PACKAGE_DIR = Path("autolinkingbrain")


def _module_docstring(path: Path) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc = ast.get_docstring(tree)
    return doc.strip() if doc else None


@pytest.mark.parametrize("rel_path", REQUIRED_LAYER_READMES)
def test_layer_readme_exists(repo_root: Path, rel_path: str) -> None:
    assert (repo_root / rel_path).is_file(), f"missing layer doc: {rel_path}"


def test_autolinkingbrain_modules_have_docstrings(repo_root: Path) -> None:
    pkg = repo_root / PACKAGE_DIR
    py_files = sorted(p for p in pkg.rglob("*.py") if p.name != "__init__.py")
    assert py_files, "expected autolinkingbrain/**/*.py modules"

    missing: list[str] = []
    for path in py_files:
        doc = _module_docstring(path)
        if not doc:
            missing.append(path.name)

    assert not missing, f"modules without docstring: {missing}"


def test_doc_coverage_ratio(repo_root: Path) -> None:
    """Soft target: ≥80% of architecture layers documented (see docs/CONTRIBUTING.md)."""
    documented = sum(1 for p in REQUIRED_LAYER_READMES if (repo_root / p).is_file())
    ratio = documented / len(REQUIRED_LAYER_READMES)
    assert ratio >= 0.8
