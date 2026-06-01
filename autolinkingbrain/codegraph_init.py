"""Run codegraph init -i across one or more repository roots."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from autolinkingbrain.mem0_project_slug import discover_repo_paths_for_workspace
from autolinkingbrain.paths import REPO_ROOT

_ROOT = REPO_ROOT


def auto_discover_enabled() -> bool:
    return os.environ.get("CODEGRAPH_AUTO_DISCOVER", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def codegraph_bin() -> str | None:
    return shutil.which("codegraph")


def _normalize_path(raw: str) -> Path | None:
    s = (raw or "").strip()
    if not s:
        return None
    p = Path(s).expanduser()
    try:
        return p.resolve()
    except OSError:
        return p


def workspace_roots_from_env() -> list[str]:
    raw = os.environ.get("CODEGRAPH_WORKSPACE", "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.replace("\n", ";").split(";") if p.strip()]


def repos_from_env() -> list[Path]:
    """Optional manual extras (CODEGRAPH_REPOS). Auto-discovery is preferred."""
    raw = os.environ.get("CODEGRAPH_REPOS", "").strip()
    if not raw:
        return []
    out: list[Path] = []
    for part in raw.replace("\n", ";").split(";"):
        p = _normalize_path(part)
        if p and p.is_dir():
            out.append(p)
    return out


def repos_from_file(path: Path | None = None) -> list[Path]:
    """Optional manual extras (codegraph_repos.txt). Auto-discovery is preferred."""
    cfg = path or (_ROOT / "codegraph_repos.txt")
    if not cfg.is_file():
        return []
    out: list[Path] = []
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        p = _normalize_path(line)
        if not p:
            p = _normalize_path(str(_ROOT / line))
        if p and p.is_dir():
            out.append(p)
    return out


def collect_repo_paths(
    *,
    paths: list[str] | None = None,
    workspace: str = "",
    discover: bool = False,
    auto_discover: bool | None = None,
    include_defaults: bool = True,
) -> list[Path]:
    """
    Resolve repo roots for CodeGraph.

    Priority:
    1. Auto-discovery (default ON) — same layout rules as Mem0 slug / session bootstrap
    2. Explicit CLI paths
    3. Optional CODEGRAPH_WORKSPACE / --workspace
    4. Optional codegraph_repos.txt and CODEGRAPH_REPOS extras
    """
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path | None) -> None:
        if p is None or not p.is_dir():
            return
        key = str(p.resolve()).lower()
        if key in seen:
            return
        seen.add(key)
        out.append(p.resolve())

    use_auto = auto_discover if auto_discover is not None else auto_discover_enabled()
    if use_auto or discover:
        ws = workspace_roots_from_env()
        if workspace:
            ws.append(workspace)
        if include_defaults and str(_ROOT) not in ws:
            ws.append(str(_ROOT))
        discovered = discover_repo_paths_for_workspace(
            workspace_roots=ws or None,
            cwd=os.getcwd(),
            extra_roots=[str(_ROOT)] if include_defaults else None,
            server_root=_ROOT,
        )
        for p in discovered:
            add(p)

    for raw in paths or []:
        add(_normalize_path(raw))
    for p in repos_from_file():
        add(p)
    for p in repos_from_env():
        add(p)

    if include_defaults:
        add(_ROOT)

    return out


def repo_has_index(repo: Path) -> bool:
    cg = repo / ".codegraph"
    if not cg.is_dir():
        return False
    try:
        return any(cg.iterdir())
    except OSError:
        return False


def init_repo(repo: Path, *, force: bool = False, timeout_sec: int = 3600) -> tuple[bool, str]:
    """Run codegraph init -i in repo. Returns (ok, message)."""
    cg = codegraph_bin()
    if not cg:
        return False, "codegraph not on PATH (install: https://github.com/colbymchenry/codegraph)"

    if repo_has_index(repo) and not force:
        return True, f"skip (already indexed): {repo}"

    try:
        proc = subprocess.run(
            [cg, "init", "-i"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_sec}s: {repo}"
    except OSError as e:
        return False, f"failed to run codegraph: {e}"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        return False, f"exit {proc.returncode}: {repo} — {err}"

    return True, f"indexed: {repo}"


def status_repo(repo: Path, *, timeout_sec: int = 120) -> tuple[bool, str]:
    cg = codegraph_bin()
    if not cg:
        return False, "codegraph not on PATH"
    if not repo_has_index(repo):
        return False, f"no index: {repo}"
    try:
        proc = subprocess.run(
            [cg, "status"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        return False, str(e)
    msg = (proc.stdout or proc.stderr or "").strip().splitlines()
    head = msg[0][:120] if msg else "(no output)"
    ok = proc.returncode == 0
    return ok, f"{repo.name}: {head}"


def list_discovered_repos(
    *,
    paths: list[str] | None = None,
    workspace: str = "",
    auto_discover: bool | None = None,
) -> list[Path]:
    return collect_repo_paths(
        paths=paths,
        workspace=workspace,
        auto_discover=auto_discover,
        include_defaults=True,
    )


def init_all(
    repos: list[Path],
    *,
    force: bool = False,
) -> int:
    if not repos:
        print("No repos discovered.", file=sys.stderr)
        print("Open a workspace folder in Cursor or set CODEGRAPH_WORKSPACE=D:\\feature", file=sys.stderr)
        return 2

    if not codegraph_bin():
        print("codegraph not on PATH.", file=sys.stderr)
        print(
            "Install: irm https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1 | iex",
            file=sys.stderr,
        )
        return 1

    failed = 0
    for repo in repos:
        print(f"-> {repo}")
        ok, msg = init_repo(repo, force=force)
        print(f"  {msg}")
        if not ok:
            failed += 1
    print(f"\nDone: {len(repos) - failed}/{len(repos)} ok")
    return 1 if failed else 0


def status_all(repos: list[Path]) -> int:
    if not codegraph_bin():
        print("codegraph not on PATH")
        return 1
    if not repos:
        repos = collect_repo_paths()
    for repo in repos:
        ok, msg = status_repo(repo)
        mark = "OK" if ok else "-"
        print(f"[{mark}] {msg}")
    return 0
