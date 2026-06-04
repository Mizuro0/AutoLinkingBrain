"""Set-and-forget project indexing outside the MCP process (subprocess / CLI)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from autolinkingbrain.codegraph_init import collect_repo_paths
from autolinkingbrain.paths import REPO_ROOT
from autolinkingbrain.project_analysis import evaluate_analysis_status, run_analysis_batch

_PROGRESS: Callable[[str], None] | None = None


def _log(msg: str) -> None:
    if _PROGRESS:
        _PROGRESS(msg)
    else:
        print(msg, file=sys.stderr, flush=True)


def _venv_python() -> Path:
    name = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    return REPO_ROOT / ".venv" / name


def analysis_subprocess_enabled() -> bool:
    v = os.environ.get("MEM0_ANALYSIS_SUBPROCESS", "").strip().lower()
    if v in ("0", "false", "no"):
        return False
    if v in ("1", "true", "yes"):
        return True
    return sys.platform == "win32"


def run_index_until_done(
    project_root: Path | str,
    *,
    mode: str = "auto",
    batch_size: int = 5,
    index_only: bool = True,
) -> dict[str, Any]:
    """Index one repo in-process (no Mem0 writes when index_only=True)."""
    from autolinkingbrain.mem0_project_slug import resolve_project_slug

    root = Path(project_root).expanduser().resolve()
    slug = resolve_project_slug(project_root=str(root))
    os.environ.setdefault("MEM0_FETCH_SQLITE", "1")
    if index_only:
        os.environ["MEM0_ANALYSIS_EMIT_SIGNALS"] = "0"

    total_processed = 0
    batches = 0
    last: dict[str, Any] = {}
    effective = mode

    while True:
        batches += 1
        last = run_analysis_batch(
            None,
            project_root=root,
            project_slug=slug,
            mode=effective if batches == 1 else "incremental",
            max_entities=batch_size,
            mem_add=None,
        )
        total_processed += int(last.get("processed") or 0)
        _log(
            f"[{slug}] batch {batches}: processed={last.get('processed')} "
            f"remaining~={last.get('remaining_estimate')} next={last.get('next')}"
        )
        if last.get("next") == "done":
            break
        if int(last.get("processed") or 0) == 0:
            break
        if batches > 5000:
            last["error"] = "batch_limit_exceeded"
            break
        effective = "incremental"

    st = evaluate_analysis_status(None, project_root=root, project_slug=slug)
    return {
        "ok": last.get("next") == "done" and not last.get("error"),
        "project_root": str(root),
        "project_slug": slug,
        "mode": mode,
        "batches": batches,
        "entities_processed": total_processed,
        "last_batch": last,
        "analysis_status": st.format_block(),
        "index_only": index_only,
    }


def run_index_subprocess(
    project_root: Path | str,
    *,
    mode: str = "auto",
    batch_size: int = 5,
    index_only: bool = True,
    until_done: bool = True,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    """Run indexing in a child process so MCP/brain_server never touches Chroma for scans."""
    root = Path(project_root).expanduser().resolve()
    py = _venv_python()
    if not py.is_file():
        py = Path(sys.executable)
    script = str(REPO_ROOT / "brain.py")
    cmd = [
        str(py),
        script,
        "analyze",
        mode if mode in ("full", "incremental", "auto") else "auto",
        "--project-root",
        str(root),
        "--json",
        "--batch-size",
        str(batch_size),
    ]
    if until_done:
        cmd.append("--until-done")
    else:
        cmd.append("--once")
    if index_only:
        cmd.append("--index-only")
    env = os.environ.copy()
    env["BRAIN_SKIP_VENV_REEXEC"] = "1"
    env.setdefault("MEM0_FETCH_SQLITE", "1")
    if index_only:
        env["MEM0_ANALYSIS_EMIT_SIGNALS"] = "0"
    _log(f"subprocess: {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec or int(os.environ.get("MEM0_ANALYSIS_SYNC_TIMEOUT", "3600")),
            cwd=str(REPO_ROOT),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "project_root": str(root),
            "error": "subprocess_timeout",
        }
    if proc.stderr:
        for line in proc.stderr.splitlines():
            _log(line)
    if proc.returncode != 0 and not proc.stdout.strip():
        return {
            "ok": False,
            "project_root": str(root),
            "error": (proc.stderr or "").strip() or f"exit_{proc.returncode}",
        }
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return {
            "ok": False,
            "project_root": str(root),
            "error": f"bad_json: {exc}",
            "stdout_tail": proc.stdout[-500:],
        }
    payload["subprocess"] = True
    payload["returncode"] = proc.returncode
    return payload


def sync_discovered_projects(
    *,
    extra_paths: list[str] | None = None,
    mode: str = "auto",
    batch_size: int = 5,
    index_only: bool = True,
    use_subprocess: bool | None = None,
) -> dict[str, Any]:
    """Index every discovered repo (CodeGraph layout). Set-and-forget entry point."""
    paths = list(extra_paths or [])
    repos = collect_repo_paths(paths=paths or None, auto_discover=True)
    if not repos:
        return {"ok": False, "error": "no_repos_discovered", "projects": []}

    subprocess_each = (
        analysis_subprocess_enabled() if use_subprocess is None else use_subprocess
    )
    results: list[dict[str, Any]] = []
    for repo in repos:
        _log(f"=== sync {repo} ===")
        if subprocess_each:
            one = run_index_subprocess(
                repo,
                mode=mode,
                batch_size=batch_size,
                index_only=index_only,
            )
        else:
            one = run_index_until_done(
                repo,
                mode=mode,
                batch_size=batch_size,
                index_only=index_only,
            )
        results.append(one)

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_count == len(results),
        "repos_total": len(results),
        "repos_ok": ok_count,
        "mode": mode,
        "index_only": index_only,
        "subprocess": subprocess_each,
        "projects": results,
    }
