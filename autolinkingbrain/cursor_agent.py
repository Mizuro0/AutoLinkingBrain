"""Install/sync Cursor agent skill and global rules from repo templates."""

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


def sync_cursor_agent_assets(*, force: bool = False) -> list[Path]:
    """Copy skill + rules to ~/.cursor/ when sources are newer (or force=True)."""
    if _sync_disabled():
        return []

    written: list[Path] = []
    try:
        home_cursor = Path.home() / ".cursor"

        if SKILL_SRC.is_file():
            skill_dest_dir = home_cursor / "skills" / SKILL_ID
            skill_dest = skill_dest_dir / "SKILL.md"
            if force or _needs_copy(SKILL_SRC, skill_dest):
                skill_dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(SKILL_SRC, skill_dest)
                written.append(skill_dest)

        if RULES_SRC_DIR.is_dir():
            rules_dest_dir = home_cursor / "rules"
            rules_dest_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted(RULES_SRC_DIR.glob("*.mdc")):
                dest = rules_dest_dir / src.name
                if force or _needs_copy(src, dest):
                    shutil.copy2(src, dest)
                    written.append(dest)
    except OSError:
        _log.debug("cursor agent asset sync skipped", exc_info=True)

    return written


def agent_assets_configured() -> bool:
    """True if global skill and at least one rule file exist."""
    home = Path.home() / ".cursor"
    skill_ok = (home / "skills" / SKILL_ID / "SKILL.md").is_file()
    rules_ok = any(home.glob("rules/autolinking-brain*.mdc"))
    return skill_ok and rules_ok
