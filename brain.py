#!/usr/bin/env python3
"""
AutoLinkingBrain — one launcher, minimal commands.

  python brain.py           viewer + browser (default)
  python brain.py status      health check
  python brain.py codegraph   index all discovered repos (CodeGraph)
  python brain.py codegraph --list   show repos only, no init
  python brain.py install     venv + MCP + hooks (no PowerShell)
  python brain.py setup       idempotent bootstrap (start.bat uses this)
  python brain.py stats       metrics / ROI estimate (offline, no agent tokens)

Double-click start.bat (Windows) or ./start.sh (Unix) — setup + viewer.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _viewer_host() -> str:
    return os.environ.get("VIEWER_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _viewer_port() -> int:
    return int(os.environ.get("VIEWER_PORT", "8501"))


def _viewer_url() -> str:
    host = _viewer_host()
    display = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{display}:{_viewer_port()}/"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except OSError:
        return False


def _ollama_ok() -> bool:
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").replace("http://", "").replace("https://", "")
    if ":" in host:
        h, p = host.rsplit(":", 1)
        port = int(p)
    else:
        h, port = host, 11434
    return _port_open(h, port)


def cmd_status(_: argparse.Namespace) -> int:
    py = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    chroma = Path(os.environ.get("MEM0_CHROMA_PATH", str(ROOT / "chroma_data")))

    print(f"repo:     {ROOT}")
    print(f"python:   {py} {'OK' if py.is_file() else 'MISSING'}")
    print(f"chroma:   {chroma} {'OK' if chroma.is_dir() else 'MISSING'}")
    print(f"ollama:   {'OK' if _ollama_ok() else 'DOWN — run ollama serve'}")
    probe = "127.0.0.1" if _viewer_host() in ("0.0.0.0", "::") else _viewer_host()
    if _port_open(probe, _viewer_port()):
        print(f"viewer:   RUNNING {_viewer_url()}")
    else:
        print("viewer:   stopped — run: python brain.py")

    sys.path.insert(0, str(ROOT))
    try:
        from autolinkingbrain.codegraph_init import collect_repo_paths, codegraph_bin

        if codegraph_bin():
            repos = collect_repo_paths()
            print(f"codegraph: {len(repos)} repo(s) discovered (python brain.py codegraph --list)")
        else:
            print("codegraph: not on PATH")
    except Exception as e:
        print(f"codegraph: {e}")

    print("\nMCP AutoLinkingBrain runs inside Cursor — not from this script.")
    return 0


def cmd_viewer(*, open_browser: bool = True) -> int:
    if not _ollama_ok():
        print("Warning: Ollama not reachable — embeddings/autolog need ollama serve", file=sys.stderr)

    probe = "127.0.0.1" if _viewer_host() in ("0.0.0.0", "::") else _viewer_host()
    if _port_open(probe, _viewer_port()):
        print(f"Viewer already running at {_viewer_url()}")
        if open_browser:
            webbrowser.open(_viewer_url())
        return 0

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(_viewer_url())).start()

    print(f"Brain viewer: {_viewer_url()}  (Ctrl+C to stop)")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from viewer_server import main

    main()
    return 0


def cmd_codegraph(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.codegraph_init import collect_repo_paths, init_all, status_all

    repos = collect_repo_paths(
        paths=args.paths,
        workspace=args.workspace,
        auto_discover=not args.no_auto,
    )

    if args.list:
        if not repos:
            print("No repos discovered.")
            return 1
        print(f"{len(repos)} repo(s):")
        for p in repos:
            print(f"  {p}")
        return 0

    if args.status_only:
        return status_all(repos)

    if not repos:
        print("No repos discovered. Set CODEGRAPH_WORKSPACE or open projects near this repo.")
        return 2

    if not args.quiet:
        print(f"Indexing {len(repos)} repo(s)…")
    return init_all(repos, force=args.force)


def cmd_install(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.brain_install import run_install

    return run_install(
        skip_venv=args.skip_venv,
        skip_mcp=args.skip_mcp,
        skip_hooks=args.skip_hooks,
        skip_ollama=args.skip_ollama,
        pull_models=args.pull_models,
        with_codegraph=args.with_codegraph,
    )


def cmd_setup(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.brain_install import run_setup

    return run_setup(
        with_codegraph=not args.no_codegraph,
        pull_models=not args.no_pull_models,
        codegraph_init=not args.no_codegraph_init,
        force_pip=args.force_pip,
    )


def cmd_viewer_with_setup(args: argparse.Namespace) -> int:
    if not getattr(args, "skip_setup", False):
        rc = cmd_setup(argparse.Namespace(
            no_codegraph=False,
            no_pull_models=False,
            no_codegraph_init=False,
            force_pip=False,
        ))
        if rc != 0:
            return rc
    return cmd_viewer(open_browser=not args.no_browser)


def cmd_sync_agent(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.cursor_agent import sync_cursor_agent_assets

    written = sync_cursor_agent_assets(ROOT, force=args.force_copy, all_discovered_repos=True)
    if written:
        for p in written:
            print(p)
    else:
        print("OK (already up to date)")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    import json as _json

    from autolinkingbrain.brain_metrics import aggregate, format_report

    report = aggregate(days=args.days)
    if args.json:
        print(_json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="brain",
        description="AutoLinkingBrain launcher — viewer, status, CodeGraph.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=("start", "status", "codegraph", "install", "setup", "stats", "sync-agent"),
        help="start=setup+viewer, setup=bootstrap, sync-agent=skill+rules to all repos, stats=metrics",
    )

    p_stats = parser.add_argument_group("stats options (with command stats)")
    p_stats.add_argument("--days", type=float, default=7.0, help="Lookback window in days (default 7)")
    p_stats.add_argument("--json", action="store_true", help="JSON output for CI/scripts")

    p_setup = parser.add_argument_group("setup options (with command setup)")
    p_setup.add_argument("--no-codegraph", action="store_true", help="Skip codegraph MCP entry")
    p_setup.add_argument("--no-pull-models", action="store_true", help="Skip ollama pull")
    p_setup.add_argument("--no-codegraph-init", action="store_true", help="Skip codegraph init for missing indexes")
    p_setup.add_argument("--force-pip", action="store_true", help="Re-run pip install")

    p_inst = parser.add_argument_group("install options (with command install)")
    p_inst.add_argument("--skip-venv", action="store_true", help="Skip venv/pip")
    p_inst.add_argument("--skip-mcp", action="store_true", help="Skip mcp.json merge")
    p_inst.add_argument("--skip-hooks", action="store_true", help="Skip hooks.json merge")
    p_inst.add_argument("--skip-ollama", action="store_true", help="Skip Ollama check")
    p_inst.add_argument("--pull-models", action="store_true", help="ollama pull llama3.2 + nomic-embed-text")
    p_inst.add_argument("--with-codegraph", action="store_true", help="Add codegraph MCP entry if on PATH")

    p_sync = parser.add_argument_group("sync-agent options (with command sync-agent)")
    p_sync.add_argument("--force-copy", action="store_true", help="Overwrite skill/rules even when up to date")

    p_cg = parser.add_argument_group("codegraph options (with command codegraph)")
    p_cg.add_argument("--list", action="store_true", help="List discovered repos only")
    p_cg.add_argument("--status", dest="status_only", action="store_true", help="CodeGraph status per repo")
    p_cg.add_argument("--force", action="store_true", help="Re-index even if .codegraph exists")
    p_cg.add_argument("--workspace", default="", help="Monorepo root (or CODEGRAPH_WORKSPACE env)")
    p_cg.add_argument("--no-auto", action="store_true", help="Disable auto-discovery")
    p_cg.add_argument("--quiet", action="store_true", help="Less output")
    p_cg.add_argument("paths", nargs="*", help="Extra repo paths")

    parser.add_argument("--no-browser", action="store_true", help="With start: do not open browser")
    parser.add_argument("--skip-setup", action="store_true", help="With start: skip bootstrap, viewer only")

    args = parser.parse_args()

    if args.command == "start":
        return cmd_viewer_with_setup(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "codegraph":
        return cmd_codegraph(args)
    if args.command == "install":
        return cmd_install(args)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "sync-agent":
        return cmd_sync_agent(args)
    if args.command == "stats":
        return cmd_stats(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
