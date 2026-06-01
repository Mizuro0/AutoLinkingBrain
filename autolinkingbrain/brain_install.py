"""Python installer for AutoLinkingBrain (alternative to install.ps1)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from autolinkingbrain.paths import REPO_ROOT as ROOT


def _mem0_env() -> dict[str, str]:
    """Env vars merged into MCP server and hook subprocesses."""
    return {"MEM0_TELEMETRY": "false"}


def _backup(path: Path) -> None:
    if path.is_file():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-{stamp}"))


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _venv_python() -> Path:
    if sys.platform == "win32":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def _ensure_venv() -> Path:
    py = _venv_python()
    if py.is_file():
        return py
    subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True, cwd=ROOT)
    if not py.is_file():
        raise RuntimeError(f"venv python missing: {py}")
    return py


def _pip_install(py: Path) -> None:
    req = ROOT / "requirements.txt"
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(req)], check=True, cwd=ROOT)
    _pip_stamp().write_text(str(req.stat().st_mtime), encoding="utf-8")


def _ollama_ok() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ollama_has_model(name: str) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False
    prefix = name.split(":")[0]
    for entry in data.get("models") or []:
        model_name = str(entry.get("name") or "")
        if model_name == name or model_name.startswith(prefix + ":") or model_name == prefix:
            return True
    return False


def _pull_ollama_models(*, only_missing: bool = True) -> None:
    if not shutil.which("ollama"):
        print("  ! ollama not in PATH")
        return
    for model in ("llama3.2", "nomic-embed-text"):
        if only_missing and _ollama_has_model(model):
            print(f"  OK: {model}")
            continue
        print(f"  ollama pull {model} …")
        subprocess.run(["ollama", "pull", model], cwd=ROOT)


def _pip_stamp() -> Path:
    return ROOT / ".venv" / ".brain_pip_ok"


def _pip_needed() -> bool:
    py = _venv_python()
    if not py.is_file():
        return True
    stamp = _pip_stamp()
    req = ROOT / "requirements.txt"
    if not stamp.is_file():
        return True
    try:
        return req.stat().st_mtime > stamp.stat().st_mtime
    except OSError:
        return True


def _mcp_configured(py: Path, *, with_codegraph: bool) -> bool:
    path = Path.home() / ".cursor" / "mcp.json"
    data = _read_json(path)
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    entry = servers.get("AutoLinkingBrain")
    if not isinstance(entry, dict):
        return False
    if str(entry.get("command", "")) != str(py):
        return False
    args = entry.get("args") or []
    if not any("brain_server.py" in str(a) for a in args):
        return False
    if with_codegraph and shutil.which("codegraph"):
        cg = servers.get("codegraph")
        if not isinstance(cg, dict) or cg.get("command") != "codegraph":
            return False
    return True


def _hooks_configured(py: Path) -> bool:
    path = Path.home() / ".cursor" / "hooks.json"
    data = _read_json(path)
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    session = hooks.get("sessionStart") or []
    if not session:
        return False
    cmd = str((session[0] or {}).get("command") or "")
    return str(py) in cmd and "session_mem0_bootstrap.py" in cmd


def _merge_hooks(py: Path) -> Path:
    path = Path.home() / ".cursor" / "hooks.json"
    _backup(path)
    data = _read_json(path)
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}

    our_cmds = (
        "session_mem0_bootstrap.py",
        "mem0_autolog_after_response.py",
        "mem0_autolog_post_tool.py",
    )

    def strip_ours(entries: list) -> list:
        out = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            cmd = str(e.get("command") or "")
            if any(x in cmd for x in our_cmds):
                continue
            out.append(e)
        return out

    session = ROOT / ".cursor" / "hooks" / "session_mem0_bootstrap.py"
    autolog = ROOT / ".cursor" / "hooks" / "mem0_autolog_after_response.py"
    post_tool = ROOT / ".cursor" / "hooks" / "mem0_autolog_post_tool.py"

    mem0_env = _mem0_env()
    hooks["sessionStart"] = [
        {"command": f'"{py}" "{session}"', "timeout": 45, "env": dict(mem0_env)}
    ] + strip_ours(list(hooks.get("sessionStart") or []))
    hooks["afterAgentResponse"] = [
        {
            "command": f'"{py}" "{autolog}"',
            "timeout": 180,
            "env": {
                **mem0_env,
                "MEM0_AUTOLOG": "1",
                "MEM0_AUTOLOG_STRICT": "1",
                "MEM0_AUTOLOG_MIN_CHARS": "400",
                "MEM0_AUTOLOG_USE_OLLAMA": "1",
                "MEM0_AUTOLOG_OLLAMA_FALLBACK": "1",
                "MEM0_AUTOLOG_TARGET": "project",
            },
        }
    ] + strip_ours(list(hooks.get("afterAgentResponse") or []))
    hooks["postToolUse"] = [
        {
            "command": f'"{py}" "{post_tool}"',
            "timeout": 45,
            "env": {**mem0_env, "MEM0_TOOLLOG": "1", "MEM0_TOOLLOG_TARGET": "project"},
        }
    ] + strip_ours(list(hooks.get("postToolUse") or []))

    _write_json(path, {"version": 1, "hooks": hooks})
    return path


def _merge_mcp(py: Path, *, with_codegraph: bool) -> Path:
    path = Path.home() / ".cursor" / "mcp.json"
    _backup(path)
    data = _read_json(path)
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    servers["AutoLinkingBrain"] = {
        "command": str(py),
        "args": [str(ROOT / "brain_server.py")],
        "cwd": "${workspaceFolder}",
        "env": _mem0_env(),
    }
    if with_codegraph and shutil.which("codegraph"):
        servers["codegraph"] = {"command": "codegraph", "args": ["serve", "--mcp"]}
        print("  + codegraph MCP entry")
    elif with_codegraph:
        print("  ! codegraph not on PATH — skipped")
    _write_json(path, {"mcpServers": servers})
    return path


def merge_cursor_config(
    py: Path | None = None,
    *,
    skip_mcp: bool = False,
    skip_hooks: bool = False,
    with_codegraph: bool = False,
) -> list[Path]:
    """Merge AutoLinkingBrain into ~/.cursor/mcp.json and hooks.json (single source for PS + Python)."""
    interpreter = py or _venv_python()
    written: list[Path] = []
    if not skip_mcp:
        written.append(_merge_mcp(interpreter, with_codegraph=with_codegraph))
    if not skip_hooks:
        written.append(_merge_hooks(interpreter))
    return written


def run_install(
    *,
    skip_venv: bool = False,
    skip_mcp: bool = False,
    skip_hooks: bool = False,
    skip_ollama: bool = False,
    pull_models: bool = False,
    with_codegraph: bool = False,
) -> int:
    print(f"AutoLinkingBrain install\nRepo: {ROOT}")

    if skip_venv:
        py = _venv_python()
        if not py.is_file():
            print("venv missing — run without --skip-venv", file=sys.stderr)
            return 1
    else:
        print("==> venv + pip")
        py = _ensure_venv()
        _pip_install(py)
        print(f"  OK: {py}")

    if not skip_ollama:
        print("==> Ollama")
        if _ollama_ok():
            print("  OK: http://127.0.0.1:11434")
            if pull_models:
                _pull_ollama_models(only_missing=False)
        else:
            print("  ! Ollama not reachable — run: ollama serve")

    if not skip_mcp:
        print("==> MCP config")
        p = _merge_mcp(py, with_codegraph=with_codegraph)
        print(f"  -> {p}")

    if not skip_hooks:
        print("==> hooks.json")
        p = _merge_hooks(py)
        print(f"  -> {p}")

    print("\nDone. Reload Cursor. Viewer: python brain.py")
    if with_codegraph or shutil.which("codegraph"):
        print("CodeGraph: python brain.py codegraph")
    return 0


def run_setup(
    *,
    with_codegraph: bool = True,
    pull_models: bool = True,
    codegraph_init: bool = True,
    force_pip: bool = False,
) -> int:
    """Idempotent first-run / start.bat bootstrap: venv, MCP, hooks, models, CodeGraph indexes."""
    print(f"AutoLinkingBrain setup\nRepo: {ROOT}")

    print("==> venv")
    py = _ensure_venv()
    if force_pip or _pip_needed():
        print("==> pip install")
        _pip_install(py)
        print(f"  OK: {py}")
    else:
        print(f"  OK: {py} (requirements unchanged)")

    if not _mcp_configured(py, with_codegraph=with_codegraph):
        print("==> MCP config")
        p = _merge_mcp(py, with_codegraph=with_codegraph)
        print(f"  -> {p}")
    else:
        print("==> MCP config OK")

    if not _hooks_configured(py):
        print("==> hooks.json")
        p = _merge_hooks(py)
        print(f"  -> {p}")
    else:
        print("==> hooks.json OK")

    print("==> Ollama")
    if _ollama_ok():
        print("  OK: http://127.0.0.1:11434")
        if pull_models:
            _pull_ollama_models(only_missing=True)
    else:
        print("  ! Ollama not reachable — run: ollama serve")

    if codegraph_init and shutil.which("codegraph"):
        from autolinkingbrain.codegraph_init import collect_repo_paths, init_all, repo_has_index

        repos = collect_repo_paths()
        missing = [r for r in repos if not repo_has_index(r)]
        if missing:
            print(f"==> CodeGraph init ({len(missing)} repo(s) without index)")
            rc = init_all(missing, force=False)
            if rc != 0:
                return rc
        elif repos:
            print(f"==> CodeGraph OK ({len(repos)} repo(s) indexed)")
        else:
            print("==> CodeGraph: no repos discovered")
    elif codegraph_init:
        print("==> CodeGraph: not on PATH (skipped)")

    print("\nSetup complete.")
    return 0
