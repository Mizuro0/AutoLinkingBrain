"""Install/sync Cursor agent skill and global rules from repo templates."""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from autolinkingbrain.paths import REPO_ROOT

SKILL_ID = "autolinking-brain-mcp"  # primary skill id (backward compat)
SOURCE_ROOT = REPO_ROOT / "config" / "cursor"
SKILLS_SRC_DIR = SOURCE_ROOT / "skills"
SKILL_SRC = SKILLS_SRC_DIR / SKILL_ID / "SKILL.md"
RULES_SRC_DIR = SOURCE_ROOT / "rules"

_log = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

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


def global_rules_dir() -> Path:
    return Path.home() / ".cursor" / "rules"


def global_skills_dir() -> Path:
    return Path.home() / ".cursor" / "skills"


def _sync_disabled() -> bool:
    return os.environ.get("MEM0_SKIP_CURSOR_AGENT_SYNC", "").strip().lower() in ("1", "true", "yes")


def project_rules_sync_enabled() -> bool:
    """Opt-in: copy rules into each workspace `.cursor/rules/` (legacy). Default off."""
    return os.environ.get("MEM0_SYNC_PROJECT_RULES", "0").strip().lower() in ("1", "true", "yes")


def mcp_start_sync_enabled() -> bool:
    """Optional sync on MCP server import (default off — use install/sync-agent instead)."""
    return os.environ.get("MEM0_MCP_START_SYNC", "0").strip().lower() in ("1", "true", "yes")


def sync_agent_all_repos_enabled() -> bool:
    """When true, `brain.py sync-agent --all-repos` scans all CodeGraph-discovered repos (slow)."""
    return os.environ.get("MEM0_SYNC_AGENT_ALL_REPOS", "0").strip().lower() in ("1", "true", "yes")


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


def _frontmatter_always_apply(text: str) -> bool:
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    fm = parts[1]
    return "alwaysApply: true" in fm or "alwaysApply:true" in fm.replace(" ", "")


def compile_always_apply_rules_context(*, max_chars: int = 4500) -> str:
    """
    Plain-text protocol from alwaysApply rules — injected by sessionStart hook
    so every workspace gets Brain protocol without per-project `.cursor/rules/`.
    """
    if not RULES_SRC_DIR.is_dir():
        return ""
    parts: list[str] = []
    for src in sorted(RULES_SRC_DIR.glob("*.mdc")):
        try:
            text = src.read_text(encoding="utf-8")
        except OSError:
            continue
        if not _frontmatter_always_apply(text):
            continue
        body = _FRONTMATTER_RE.sub("", text, count=1).strip()
        if body:
            parts.append(body)
    if not parts:
        return ""
    out = "## AutoLinkingBrain protocol (global)\n\n" + "\n\n---\n\n".join(parts)
    if len(out) > max_chars:
        out = out[: max_chars - 40] + "\n\n… [protocol truncated]\n"
    return out


def sync_global_skill(*, force: bool = False) -> list[Path]:
    """Copy all skills from config/cursor/skills/*/SKILL.md to ~/.cursor/skills/."""
    if _sync_disabled() or not SKILLS_SRC_DIR.is_dir():
        return []
    written: list[Path] = []
    try:
        home_skills = global_skills_dir()
        for src in sorted(SKILLS_SRC_DIR.glob("*/SKILL.md")):
            skill_id = src.parent.name
            skill_dest = home_skills / skill_id / "SKILL.md"
            if force or _needs_copy(src, skill_dest):
                skill_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, skill_dest)
                written.append(skill_dest)
    except OSError:
        _log.debug("global skill sync skipped", exc_info=True)
    return written


def sync_global_rules(*, force: bool = False) -> list[Path]:
    """Copy rules to ~/.cursor/rules/ — one global install, all workspaces."""
    if _sync_disabled():
        return []
    try:
        return _copy_rules_to(global_rules_dir(), force=force)
    except OSError:
        _log.debug("global rules sync skipped", exc_info=True)
        return []


def sync_global_agent_assets(*, force: bool = False) -> list[Path]:
    """Global skill + global rules only (default for install/onboard/hooks)."""
    written = sync_global_skill(force=force)
    written.extend(sync_global_rules(force=force))
    return written


def sync_project_rules(workspace_root: Path | None = None, *, force: bool = False) -> list[Path]:
    """Legacy: copy rules to <workspace>/.cursor/rules/ — requires MEM0_SYNC_PROJECT_RULES=1."""
    if _sync_disabled() or not project_rules_sync_enabled():
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
    """Legacy opt-in: sync rules to workspace roots when MEM0_SYNC_PROJECT_RULES=1."""
    if not project_rules_sync_enabled():
        return sync_global_agent_assets(force=force)

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
    """Legacy: push rules to all CodeGraph-discovered repos (MEM0_SYNC_PROJECT_RULES=1)."""
    if _sync_disabled() or not project_rules_sync_enabled():
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
    """
    Sync global skill + global rules (~/.cursor/).

    Per-project `.cursor/rules/` only when MEM0_SYNC_PROJECT_RULES=1 or --all-repos
    with that env (legacy).
    """
    written = sync_global_agent_assets(force=force)
    if project_rules_sync_enabled():
        written.extend(sync_project_rules(workspace_root, force=force))
        if all_discovered_repos:
            written.extend(sync_rules_to_discovered_repos(force=force))
    return written


def sync_mcp_startup_if_enabled(workspace_root: Path | None = None) -> list[Path]:
    """Minimal global sync when MEM0_MCP_START_SYNC=1."""
    if not mcp_start_sync_enabled() or _sync_disabled():
        return []
    return sync_global_agent_assets(force=False)


def agent_assets_configured(workspace_root: Path | None = None) -> bool:
    """True if global skill and global Brain rules exist under ~/.cursor/."""
    _ = workspace_root
    home = Path.home() / ".cursor"
    skill_ok = (home / "skills" / SKILL_ID / "SKILL.md").is_file()
    rules_dir = home / "rules"
    rules_ok = rules_dir.is_dir() and any(rules_dir.glob("autolinking-brain*.mdc"))
    return skill_ok and rules_ok
