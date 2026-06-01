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


def sync_cursor_agent_assets(
    workspace_root: Path | None = None,
    *,
    force: bool = False,
) -> list[Path]:
    """Sync global skill + project rules for the given workspace (default: cwd)."""
    written = sync_global_skill(force=force)
    written.extend(sync_project_rules(workspace_root, force=force))
    return written


def agent_assets_configured(workspace_root: Path | None = None) -> bool:
    """True if global skill exists and workspace has project rule file."""
    home = Path.home() / ".cursor"
    skill_ok = (home / "skills" / SKILL_ID / "SKILL.md").is_file()
    root = (workspace_root or REPO_ROOT).resolve()
    rules_ok = any((root / ".cursor" / "rules").glob("autolinking-brain*.mdc"))
    return skill_ok and rules_ok
