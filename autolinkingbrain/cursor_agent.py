"""Install/sync Cursor agent skill and project rules from repo templates."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from autolinkingbrain.paths import REPO_ROOT

SKILL_ID = "autolinking-brain-mcp"
SOURCE_ROOT = REPO_ROOT / "config" / "cursor"
SKILL_SRC = SOURCE_ROOT / "skills" / SKILL_ID / "SKILL.md"
RULES_SRC_DIR = SOURCE_ROOT / "rules"

_log = logging.getLogger(__name__)

_SKIP_RULE_DIR_NAMES = frozenset(
    {
        "__pycache__",
        "node_modules",
        "chroma_data",
        ".venv",
        "venv",
        ".git",
        ".understand-anything",
    }
)


def _eligible_rule_sync_root(repo: Path) -> bool:
    """Only git roots or monorepo subprojects — not random subfolders of AutoLinkingBrain."""
    if not repo.is_dir():
        return False
    name = repo.name.lower()
    if name.startswith(".") or name in _SKIP_RULE_DIR_NAMES:
        return False

    try:
        resolved = repo.resolve()
    except OSError:
        resolved = repo

    git = resolved / ".git"
    if git.exists() or git.is_file():
        return True

    from autolinkingbrain.mem0_project_slug import _should_skip_repo_path, looks_like_project_dir

    if _should_skip_repo_path(resolved) or not looks_like_project_dir(resolved):
        return False

    try:
        server = REPO_ROOT.resolve()
        if resolved != server and server in resolved.parents:
            return False
    except OSError:
        pass

    return True


def _sync_disabled() -> bool:
    return os.environ.get("MEM0_SKIP_CURSOR_AGENT_SYNC", "").strip().lower() in ("1", "true", "yes")


def _needs_copy(src: Path, dest: Path) -> bool:
    if not dest.is_file():
        return True
    try:
        s = src.stat()
        d = dest.stat()
    except OSError:
        return True
    return s.st_mtime > d.st_mtime or s.st_size != d.st_size


def _copy_rules_to(rules_dest_dir: Path, *, force: bool) -> list[Path]:
    written: list[Path] = []
    if not RULES_SRC_DIR.is_dir():
        return written
    rules_dest_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(RULES_SRC_DIR.glob("*.mdc")):
        dest = rules_dest_dir / src.name
        if force or _needs_copy(src, dest):
            shutil.copy2(src, dest)
            written.append(dest)
    return written


def sync_global_skill(*, force: bool = False) -> list[Path]:
    """Copy agent skill to ~/.cursor/skills/ (global, all workspaces)."""
    if _sync_disabled() or not SKILL_SRC.is_file():
        return []
    written: list[Path] = []
    try:
        skill_dest_dir = Path.home() / ".cursor" / "skills" / SKILL_ID
        skill_dest = skill_dest_dir / "SKILL.md"
        if force or _needs_copy(SKILL_SRC, skill_dest):
            skill_dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SKILL_SRC, skill_dest)
            written.append(skill_dest)
    except OSError:
        _log.debug("global skill sync skipped", exc_info=True)
    return written


def sync_project_rules(workspace_root: Path | None = None, *, force: bool = False) -> list[Path]:
    """Copy rules to <workspace>/.cursor/rules/ — visible in Cursor Settings → Project Rules."""
    if _sync_disabled():
        return []
    root = (workspace_root or Path.cwd()).resolve()
    try:
        return _copy_rules_to(root / ".cursor" / "rules", force=force)
    except OSError:
        _log.debug("project rules sync skipped for %s", root, exc_info=True)
        return []


def sync_project_rules_for_workspace_roots(
    workspace_roots: list | None,
    *,
    cwd: str | None = None,
    force: bool = False,
) -> list[Path]:
    """Sync rules to every workspace root from a Cursor hook or MCP roots payload."""
    if _sync_disabled():
        return []

    written: list[Path] = []
    seen: set[str] = set()
    candidates: list[Path] = []

    if isinstance(workspace_roots, list):
        for raw in workspace_roots:
            if raw:
                candidates.append(Path(str(raw)))
    if cwd:
        candidates.append(Path(cwd))

    for root in candidates:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        written.extend(sync_project_rules(resolved, force=force))

    return written


def sync_rules_to_discovered_repos(*, force: bool = False) -> list[Path]:
    """Push rules to all repos found by the same auto-discovery as CodeGraph/Mem0 slug."""
    if _sync_disabled():
        return []

    written: list[Path] = []
    try:
        from autolinkingbrain.codegraph_init import collect_repo_paths

        for repo in collect_repo_paths(dedupe_by_name=False):
            if _eligible_rule_sync_root(repo):
                written.extend(sync_project_rules(repo, force=force))
    except OSError:
        _log.debug("discovered repo rules sync skipped", exc_info=True)

    return written


def sync_cursor_agent_assets(
    workspace_root: Path | None = None,
    *,
    force: bool = False,
    all_discovered_repos: bool = False,
) -> list[Path]:
    """Sync global skill + project rules for workspace(s)."""
    written = sync_global_skill(force=force)
    written.extend(sync_project_rules(workspace_root, force=force))
    if all_discovered_repos:
        written.extend(sync_rules_to_discovered_repos(force=force))
    return written


def agent_assets_configured(workspace_root: Path | None = None) -> bool:
    """True if global skill exists and workspace has project rule file."""
    home = Path.home() / ".cursor"
    skill_ok = (home / "skills" / SKILL_ID / "SKILL.md").is_file()
    root = (workspace_root or REPO_ROOT).resolve()
    rules_ok = any((root / ".cursor" / "rules").glob("autolinking-brain*.mdc"))
    return skill_ok and rules_ok
