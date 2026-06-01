"""Resolve Mem0 project_<slug> from workspace layout, git roots, and file paths.

When several repos live under one Cursor folder (e.g. feature/backend, feature/crm),
slug must be the child repo name — not the parent folder name.
"""
from __future__ import annotations

import os
import pathlib
import re
from urllib.parse import unquote, urlparse

_SLUG_OVERRIDE_RE = re.compile(r"^[a-zA-Z0-9_.\-]{1,80}$")

_PROJECT_DIR_MARKERS = (
    "package.json",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "composer.json",
    "Gemfile",
)

_PATH_IN_TEXT_RE = re.compile(
    r"(?:^|[\s\"'`(])"
    r"("
    r"[A-Za-z]:\\[^\s\"'`<>|]+"
    r"|/[^\s\"'`<>|]+"
    r"|[a-zA-Z][\w.\-]*(?:[/\\][\w.\-/\\]+)+"
    r")",
)


def _env_name_set(key: str) -> set[str]:
    """Lowercase path segment / folder names from a semicolon- or comma-separated env var."""
    raw = os.environ.get(key, "").strip()
    if not raw:
        return set()
    parts: list[str] = []
    for chunk in raw.replace(",", ";").split(";"):
        name = chunk.strip().lower()
        if name:
            parts.append(name)
    return set(parts)


def sanitize_slug(raw: str) -> str:
    t = (raw or "").strip().replace(" ", "_")
    if _SLUG_OVERRIDE_RE.fullmatch(t):
        return t
    out: list[str] = []
    for c in t:
        if c.isalnum() or c in "_-.":
            out.append(c)
        elif c.isspace():
            out.append("_")
    r = "".join(out).strip("._-")[:80]
    return r or "unknown_workspace"


def path_from_mcp_root_uri(uri: str) -> pathlib.Path | None:
    try:
        u = urlparse(uri)
        if u.scheme != "file":
            return None
        p = pathlib.Path(unquote(u.path))
        return p if str(p) else None
    except Exception:
        return None


def slug_from_git_marker(start_path: pathlib.Path) -> str | None:
    try:
        current = start_path.resolve()
    except Exception:
        current = start_path

    if current.is_file():
        current = current.parent

    while True:
        marker = current / ".git"
        if marker.is_dir() or marker.is_file():
            name = current.name.strip()
            return sanitize_slug(name) if name else None
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def looks_like_project_dir(path: pathlib.Path) -> bool:
    if not path.is_dir():
        return False
    return any((path / name).exists() for name in _PROJECT_DIR_MARKERS)


def normalize_workspace_roots(
    workspace_roots: list[str] | None = None,
    cwd: str | None = None,
    extra_roots: list[str] | None = None,
) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        s = (raw or "").strip()
        if not s:
            return
        try:
            p = pathlib.Path(s).resolve()
        except Exception:
            p = pathlib.Path(s)
        key = str(p).lower()
        if key in seen:
            return
        seen.add(key)
        out.append(p)

    for r in workspace_roots or []:
        if isinstance(r, str):
            _add(r)
    for r in extra_roots or []:
        if isinstance(r, str):
            _add(r)
    if cwd:
        _add(cwd)
    return out


def slug_from_path_under_roots(path: pathlib.Path, roots: list[pathlib.Path]) -> str | None:
    """Map file path -> child repo slug under a multi-project workspace root."""
    best: str | None = None
    best_len = -1

    for root in roots:
        candidates: list[pathlib.Path] = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.append(root / path)
            try:
                candidates.append(path.resolve())
            except Exception:
                pass

        for fp in candidates:
            rel = None
            for base in (root, *([root.resolve()] if str(root) else [])):
                try:
                    rel = fp.relative_to(base)
                    break
                except ValueError:
                    continue
            if rel is None or not rel.parts:
                continue
            first = rel.parts[0]
            candidate = root / first
            git_slug = slug_from_git_marker(candidate)
            slug = git_slug or sanitize_slug(first)
            depth = len(rel.parts)
            if depth > best_len:
                best_len = depth
                best = slug
    return best


def resolve_project_slug(
    *,
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    workspace_roots: list[str] | None = None,
    cwd: str | None = None,
    extra_roots: list[str] | None = None,
) -> str:
    """
    Priority:
    1. explicit project_slug / project_root
    2. context_path -> git root or child under workspace root
    3. MEM0_PROJECT_SLUG / MCP_PROJECT_SLUG
    4. .cursor/mem0_project_slug in cwd
    5. git root from cwd
    6. child repo under workspace root from cwd
    7. basename(first workspace root)
    8. basename(cwd)
    """
    explicit = (project_slug or "").strip()
    if explicit:
        return sanitize_slug(explicit)

    root_raw = (project_root or "").strip()
    if root_raw:
        slug = sanitize_slug(pathlib.Path(root_raw).name)
        if slug != "unknown_workspace":
            return slug

    roots = normalize_workspace_roots(workspace_roots, cwd, extra_roots)

    ctx = (context_path or "").strip()
    if ctx:
        cp = pathlib.Path(ctx)
        if roots:
            child = slug_from_path_under_roots(cp, roots)
            if child:
                return child
        git_slug = slug_from_git_marker(cp)
        if git_slug:
            return git_slug

    for key in ("MEM0_PROJECT_SLUG", "MCP_PROJECT_SLUG"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return sanitize_slug(raw)

    cwd_path = pathlib.Path(cwd or os.getcwd())
    marker = cwd_path / ".cursor" / "mem0_project_slug"
    if marker.is_file():
        try:
            for line in marker.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    return sanitize_slug(s)
        except OSError:
            pass

    git_slug = slug_from_git_marker(cwd_path)
    if git_slug:
        return git_slug

    if roots:
        child = slug_from_path_under_roots(cwd_path, roots)
        if child:
            return child
        if len(roots) == 1:
            only = roots[0]
            if only.is_dir():
                try:
                    rel = cwd_path.resolve().relative_to(only.resolve())
                    if rel.parts:
                        first = only / rel.parts[0]
                        gs = slug_from_git_marker(first)
                        if gs:
                            return gs
                        if looks_like_project_dir(first):
                            return sanitize_slug(first.name)
                except ValueError:
                    pass

    if roots:
        name = roots[0].name.strip()
        if name:
            return sanitize_slug(name)

    return sanitize_slug(cwd_path.name or "unknown_workspace")


def discover_project_slugs_for_workspace(
    workspace_roots: list[str] | None = None,
    cwd: str | None = None,
    extra_roots: list[str] | None = None,
) -> list[str]:
    """All repo slugs under workspace (for session bootstrap in monorepo folders)."""
    roots = normalize_workspace_roots(workspace_roots, cwd, extra_roots)
    found: set[str] = set()

    for root in roots:
        child_repos = _direct_child_repos(root)
        if child_repos:
            for child in child_repos:
                cgs = slug_from_git_marker(child)
                if cgs:
                    found.add(cgs)
                elif looks_like_project_dir(child):
                    found.add(sanitize_slug(child.name))
            continue
        gs = slug_from_git_marker(root)
        if gs:
            found.add(gs)
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            children = []
        for child in children:
            if not child.is_dir() or child.name.startswith("."):
                continue
            cgs = slug_from_git_marker(child)
            if cgs:
                found.add(cgs)
            elif looks_like_project_dir(child):
                found.add(sanitize_slug(child.name))

    if not found and roots:
        found.add(sanitize_slug(roots[0].name))

    return sorted(found)


def _should_skip_repo_path(path: pathlib.Path) -> bool:
    """Skip bare git dirs and optional exclude list (CODEGRAPH_EXCLUDE_NAMES)."""
    name = path.name.lower()
    if name.endswith(".git"):
        return True
    if name in _env_name_set("CODEGRAPH_EXCLUDE_NAMES"):
        return True
    skip_parts = _env_name_set("CODEGRAPH_EXCLUDE_PATHS")
    if skip_parts & {part.lower() for part in path.parts}:
        return True
    return False


def _looks_like_repo_container(path: pathlib.Path) -> bool:
    """Structural: folder groups multiple distinct child repos (no name list required)."""
    return len(_direct_child_repos(path)) >= 2


def _should_scan_sibling_container(path: pathlib.Path) -> bool:
    """
    Deep-scan a sibling folder for nested repos.

    CODEGRAPH_CONTAINER_NAMES — explicit folder names (optional).
    When unset, only folders with 2+ child repos qualify (structural heuristic).
    """
    explicit = _env_name_set("CODEGRAPH_CONTAINER_NAMES")
    if explicit:
        return path.name.lower() in explicit
    return _looks_like_repo_container(path)


def _direct_child_repos(path: pathlib.Path) -> list[pathlib.Path]:
    """Immediate subfolders that are distinct repos (monorepo / copy container layout)."""
    if not path.is_dir():
        return []
    try:
        parent_slug = slug_from_git_marker(path) or sanitize_slug(path.name)
    except Exception:
        parent_slug = sanitize_slug(path.name)
    out: list[pathlib.Path] = []
    try:
        children = list(path.iterdir())
    except OSError:
        return out
    for child in children:
        if not child.is_dir() or child.name.startswith("."):
            continue
        child_slug = slug_from_git_marker(child)
        if child_slug and child_slug != parent_slug:
            out.append(child)
        elif looks_like_project_dir(child) and sanitize_slug(child.name) != parent_slug:
            out.append(child)
    return out


def _dedupe_repo_paths_by_name(paths: list[pathlib.Path]) -> list[pathlib.Path]:
    """
    One path per project folder name.

    CODEGRAPH_DEPRIORITIZE_PATHS — path segments that lose ties (e.g. archive copies).
    CODEGRAPH_PREFER_PATHS — path segments that win ties (e.g. your primary workspace root).
    """
    deprioritize = _env_name_set("CODEGRAPH_DEPRIORITIZE_PATHS")
    prefer = _env_name_set("CODEGRAPH_PREFER_PATHS")

    def score(p: pathlib.Path) -> tuple:
        parts_lower = {part.lower() for part in p.parts}
        return (
            1 if deprioritize and parts_lower & deprioritize else 0,
            0 if prefer and parts_lower & prefer else (1 if prefer else 0),
            len(p.parts),
            str(p).lower(),
        )

    by_name: dict[str, pathlib.Path] = {}
    for p in paths:
        if _should_skip_repo_path(p):
            continue
        key = sanitize_slug(p.name)
        prev = by_name.get(key)
        if prev is None or score(p) < score(prev):
            by_name[key] = p
    return sorted(by_name.values(), key=lambda p: p.name.lower())


def _scan_repo_tree(root: pathlib.Path, register, *, max_depth: int, depth: int = 0) -> None:
    """Walk workspace tree; register git roots and project-marker dirs."""
    if depth >= max_depth or not root.is_dir():
        return
    try:
        children = list(root.iterdir())
    except OSError:
        return
    for child in children:
        if not child.is_dir() or child.name.startswith("."):
            continue
        if slug_from_git_marker(child) or looks_like_project_dir(child):
            register(child)
        elif depth + 1 < max_depth:
            _scan_repo_tree(child, register, max_depth=max_depth, depth=depth + 1)


def discover_repo_paths_for_workspace(
    workspace_roots: list[str] | None = None,
    cwd: str | None = None,
    extra_roots: list[str] | None = None,
    *,
    server_root: str | pathlib.Path | None = None,
    scan_siblings: bool | None = None,
    scan_depth: int | None = None,
) -> list[pathlib.Path]:
    """
    Filesystem paths of repos under workspace(s) — same rules as discover_project_slugs_for_workspace.

    Also scans sibling git repos next to server_root (e.g. ../backend when AutoLinkingBrain
    lives alongside other clones in ~/projects).
    """
    if scan_siblings is None:
        scan_siblings = os.environ.get("CODEGRAPH_SCAN_SIBLINGS", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
    if scan_depth is None:
        scan_depth = max(0, min(int(os.environ.get("CODEGRAPH_SCAN_DEPTH", "2")), 4))

    roots = normalize_workspace_roots(workspace_roots, cwd, extra_roots)
    found: dict[str, pathlib.Path] = {}

    def register(raw: pathlib.Path) -> None:
        try:
            p = raw.resolve()
        except OSError:
            p = raw
        if not p.is_dir() or _should_skip_repo_path(p):
            return

        child_repos = _direct_child_repos(p)
        if child_repos:
            for child in child_repos:
                if _should_skip_repo_path(child):
                    continue
                try:
                    cp = child.resolve()
                except OSError:
                    cp = child
                if slug_from_git_marker(cp) or looks_like_project_dir(cp):
                    found[str(cp).lower()] = cp
            return

        if slug_from_git_marker(p) or looks_like_project_dir(p):
            if not _should_skip_repo_path(p):
                found[str(p).lower()] = p

    for root in roots:
        register(root)
        _scan_repo_tree(root, register, max_depth=scan_depth)

    if scan_siblings and server_root:
        try:
            anchor = pathlib.Path(server_root).resolve()
        except OSError:
            anchor = pathlib.Path(server_root)
        register(anchor)
        parent = anchor.parent
        if parent.is_dir() and parent != anchor:
            try:
                siblings = list(parent.iterdir())
            except OSError:
                siblings = []
            for sib in siblings:
                if not sib.is_dir() or sib.name.startswith("."):
                    continue
                if _should_scan_sibling_container(sib):
                    register(sib)
                    _scan_repo_tree(sib, register, max_depth=max(scan_depth, 1))
                elif slug_from_git_marker(sib) or looks_like_project_dir(sib):
                    register(sib)

    return _dedupe_repo_paths_by_name(list(found.values()))


def extract_context_paths_from_text(text: str, limit: int = 8) -> list[str]:
    """Pull plausible file paths from agent text for slug routing."""
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _PATH_IN_TEXT_RE.finditer(text):
        p = (m.group(1) or "").strip().rstrip(".,;:)\"']")
        if len(p) < 4 or p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= limit:
            break
    return out


def resolve_slug_from_hook_payload(data: dict, tool_input: dict | None = None) -> str:
    """Hook helper: workspace_roots + cwd + optional tool file path."""
    roots = data.get("workspace_roots") if isinstance(data.get("workspace_roots"), list) else None
    cwd = str(data.get("cwd") or "")
    ctx = ""
    if isinstance(tool_input, dict):
        for key in ("path", "target_file", "file_path", "filePath", "relative_workspace_path"):
            v = tool_input.get(key)
            if isinstance(v, str) and v.strip():
                ctx = v.strip()
                break
    if not ctx:
        for p in extract_context_paths_from_text(str(data.get("text") or ""), limit=3):
            ctx = p
            break
    return resolve_project_slug(context_path=ctx, workspace_roots=roots, cwd=cwd or None)


def effective_context_path(context_path: str = "", *text_blobs: str, limit: int = 3) -> str:
    """Use explicit context_path or infer first file path from tool text fields."""
    ctx = (context_path or "").strip()
    if ctx:
        return ctx
    for blob in text_blobs:
        for p in extract_context_paths_from_text(blob or "", limit=limit):
            return p
    return ""
