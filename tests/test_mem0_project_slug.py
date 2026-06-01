from __future__ import annotations

from autolinkingbrain.mem0_project_slug import (
    _env_name_set,
    resolve_project_slug,
    sanitize_slug,
)


def test_sanitize_slug_plain() -> None:
    assert sanitize_slug("My Project") == "My_Project"
    assert sanitize_slug("backend-api") == "backend-api"


def test_sanitize_slug_strips_unsafe_chars() -> None:
    assert sanitize_slug("foo@bar#baz") == "foobarbaz"


def test_sanitize_slug_empty_fallback() -> None:
    assert sanitize_slug("@@@") == "unknown_workspace"


def test_env_name_set_parses_semicolons_and_commas(monkeypatch) -> None:
    monkeypatch.setenv("CODEGRAPH_EXCLUDE_NAMES", "Python; node_modules , .venv")
    assert _env_name_set("CODEGRAPH_EXCLUDE_NAMES") == {"python", "node_modules", ".venv"}


def test_env_name_set_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("CODEGRAPH_CONTAINER_NAMES", raising=False)
    assert _env_name_set("CODEGRAPH_CONTAINER_NAMES") == set()


def test_resolve_project_slug_explicit() -> None:
    assert resolve_project_slug(project_slug="MyApp") == "MyApp"


def test_resolve_project_slug_from_context_path(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "monorepo"
    backend = ws / "backend"
    backend.mkdir(parents=True)
    (backend / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    file_path = backend / "src" / "main.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('hi')", encoding="utf-8")

    slug = resolve_project_slug(
        context_path=str(file_path),
        workspace_roots=[str(ws)],
        cwd=str(ws),
    )
    assert slug == "backend"
