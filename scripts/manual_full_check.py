#!/usr/bin/env python3
"""Manual E2E check — invoke real code paths (not pytest). Run: python scripts/manual_full_check.py"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MEM0_TELEMETRY", "false")
os.environ.setdefault("MEM0_CHROMA_PATH", str(ROOT / "chroma_data"))
os.environ.setdefault("MEM0_FETCH_SQLITE", "1")
os.environ.setdefault("MEM0_AUTOLOG_BACKEND", "sqlite")
os.environ.setdefault("MEM0_AUTOLOG_USE_OLLAMA", "0")

PY = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
BRAIN = [str(PY), str(ROOT / "brain.py")]


@dataclass
class Row:
    area: str
    name: str
    status: str  # OK | FAIL | SKIP | WARN
    detail: str = ""
    ms: int = 0


REPORT: list[Row] = []


def record(area: str, name: str, status: str, detail: str = "", ms: int = 0) -> None:
    REPORT.append(Row(area, name, status, detail[:500], ms))
    mark = {"OK": "+", "FAIL": "X", "SKIP": "-", "WARN": "!"}.get(status, "?")
    print(f"  [{mark}] {area} :: {name}" + (f" — {detail[:120]}" if detail else ""))


def run_cli(args: list[str], *, timeout: int = 120) -> tuple[int, str]:
    t0 = time.perf_counter()
    env = {**os.environ, "PYTHONUTF8": "1", "MEM0_FETCH_SQLITE": "1"}
    try:
        r = subprocess.run(
            BRAIN + args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out.strip()[:800]
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as exc:
        return -1, str(exc)
    finally:
        pass


def http_get(url: str, *, headers: dict | None = None, timeout: float = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(5000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def check_cli() -> None:
    section("CLI brain.py")
    cmds = [
        (["status"], 30),
        (["doctor"], 60),
        (["stats", "--json"], 45),
        (["health"], 90),
        (["context", "pack", "--query", "architecture MCP viewer"], 90),
        (["gc", "audit", "--json"], 120),
        (["gc", "purge-indexing"], 120),
        (["gc", "dedupe-exact"], 60),
        (["migrate-autolog", "--dry-run"], 120),
        (["analyze", "status"], 60),
        (["analyze", "auto", "--once", "--batch-size", "1", "--index-only"], 120),
        (["codegraph", "--list"], 60),
        (["sync-agent"], 90),
        (["mcp", "status"], 30),
    ]
    for args, timeout in cmds:
        name = " ".join(args)
        t0 = time.perf_counter()
        code, out = run_cli(args, timeout=timeout)
        ms = int((time.perf_counter() - t0) * 1000)
        if code == 0:
            record("CLI", name, "OK", out[:200], ms)
        else:
            record("CLI", name, "FAIL", f"exit={code} {out[:200]}", ms)


def _mcp_chroma_subprocess(script: str) -> tuple[bool, str]:
    """Run chroma/mem0 work in a child process so Windows AV on chromadb does not kill the runner."""
    code = f"""
import asyncio, json, os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, {json.dumps(str(ROOT))})
os.environ.setdefault("MEM0_TELEMETRY", "false")
{script}
"""
    try:
        r = subprocess.run(
            [str(PY), "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )
        out = (r.stdout or "").strip()
        if r.returncode == 0 and out.startswith("OK:"):
            return True, out[3:].strip()[:200]
        return False, f"exit={r.returncode} {(r.stderr or out)[:200]}"
    except subprocess.TimeoutExpired:
        return False, "timeout 180s"
    except Exception as exc:
        return False, str(exc)


def check_mcp_sqlite_gc() -> None:
    section("MCP paths (sqlite gc + autolog)")
    try:
        from autolinkingbrain.mem0_gc import audit_channel, list_duplicates

        report = audit_channel(None, "project_mcp_server")
        groups = list_duplicates(None, "project_mcp_server")
        record(
            "MCP",
            "auditKnowledge+listDuplicates (sqlite)",
            "OK",
            f"total={report.total} dup_groups={len(groups)}",
        )
    except Exception as exc:
        record("MCP", "auditKnowledge+listDuplicates (sqlite)", "FAIL", str(exc))


def check_mcp_direct() -> None:
    section("MCP tools (direct McpContext)")
    check_mcp_sqlite_gc()

    try:
        from autolinkingbrain.autolog_store import append_entry, list_recent, search_entries

        eid = append_entry("mcp_server", "manual_e2e", "[CURSOR] [AUT_LOG] manual probe", workspace_root=ROOT)
        recent = list_recent("mcp_server", limit=3, workspace_root=ROOT)
        found = search_entries("manual probe", project_slug="mcp_server", limit=5, workspace_root=ROOT)
        record("MCP", "autolog_store", "OK" if eid and recent else "FAIL", f"id={eid} recent={len(recent)} found={len(found)}")
    except Exception as exc:
        record("MCP", "autolog_store", "FAIL", str(exc))

    try:
        from autolinkingbrain.mcp_tools.architecture_tools import register as arch_reg
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        arch_reg(mcp)
        record("MCP", "architecture_tools register", "OK")
    except Exception as exc:
        record("MCP", "architecture_tools register", "FAIL", str(exc))


def _start_test_viewer(port: int) -> subprocess.Popen | None:
    """Fresh viewer with current code (avoids stale process hanging on /api/metrics)."""
    env = {
        **os.environ,
        "VIEWER_PORT": str(port),
        "MEM0_FETCH_SQLITE": "1",
        "PYTHONUTF8": "1",
        "MEM0_METRICS_ASYNC": "1",
    }
    try:
        proc = subprocess.Popen(
            [str(PY), str(ROOT / "viewer_server.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        record("Viewer", "server start", "FAIL", str(exc))
        return None
    for _ in range(40):
        code, _ = http_get(f"http://127.0.0.1:{port}/api/health", timeout=2)
        if code == 200:
            return proc
        time.sleep(0.5)
    proc.terminate()
    record("Viewer", "server start", "FAIL", f"health timeout on port {port}")
    return None


def check_viewer(port: int = 18501) -> None:
    section("Brain Viewer HTTP")
    proc = _start_test_viewer(port)
    if proc is None:
        return
    record("Viewer", "server", "OK", f"test port {port}")
    base = f"http://127.0.0.1:{port}"
    try:
        for path, tmo in [
            ("/api/health", 15),
            ("/api/memories", 120),
            ("/api/metrics?days=1&recent=10", 30),
            ("/api/autolog?limit=5", 15),
            ("/api/autolog/projects", 15),
            ("/", 15),
        ]:
            code, body = http_get(f"{base}{path}", timeout=tmo)
            if code == 200:
                try:
                    if path.endswith("/") or "autolog" in path and "projects" not in path:
                        preview = body[:80]
                    else:
                        data = json.loads(body)
                        preview = str(list(data.keys())[:6])
                except json.JSONDecodeError:
                    preview = f"len={len(body)}"
                record("Viewer", f"GET {path}", "OK", preview)
            else:
                record("Viewer", f"GET {path}", "FAIL", f"HTTP {code} {body[:100]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_hooks() -> None:
    section("Cursor hooks (mock stdin)")
    hooks = [
        ("session_mem0_bootstrap.py", "{}"),
        (
            "mem0_autolog_after_response.py",
            json.dumps(
                {
                    "conversation_id": "e2e-test",
                    "generation_id": "gen1",
                    "text": "x" * 500,
                    "workspace_roots": [str(ROOT)],
                    "cwd": str(ROOT),
                }
            ),
        ),
        (
            "mem0_autolog_post_tool.py",
            json.dumps(
                {
                    "tool_name": "Read",
                    "tool_input": {"path": "brain_server.py"},
                    "tool_output": "line1",
                    "cwd": str(ROOT),
                    "workspace_roots": [str(ROOT)],
                    "conversation_id": "e2e-tool",
                }
            ),
        ),
    ]
    for script, stdin_data in hooks:
        path = ROOT / ".cursor" / "hooks" / script
        if not path.is_file():
            record("Hooks", script, "SKIP", "missing")
            continue
        env = {**os.environ, "MEM0_AUTOLOG": "1", "MEM0_TOOLLOG": "1", "MEM0_SESSION_BOOTSTRAP": "1"}
        try:
            r = subprocess.run(
                [str(PY), str(path)],
                input=stdin_data,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=90,
                env=env,
                encoding="utf-8",
            )
            if r.returncode == 0:
                record("Hooks", script, "OK", (r.stdout or r.stderr or "")[:80])
            else:
                record("Hooks", script, "FAIL", (r.stderr or r.stdout or "")[:150])
        except subprocess.TimeoutExpired:
            record("Hooks", script, "FAIL", "timeout 90s")
        except Exception as exc:
            record("Hooks", script, "FAIL", str(exc))


def check_imports() -> None:
    section("Entry points import")
    modules = [
        "brain_server",
        "viewer_server",
        "qwen_review_server",
        "brain_fleet_server",
        "architecture_curator_server",
    ]
    for mod in modules:
        try:
            subprocess.run(
                [str(PY), "-c", f"import {mod}"],
                cwd=str(ROOT),
                check=True,
                capture_output=True,
                timeout=60,
            )
            record("Import", mod, "OK")
        except Exception as exc:
            record("Import", mod, "FAIL", str(exc)[:200])


def check_ollama_reviewer() -> None:
    section("Qwen Reviewer (optional)")
    from autolinkingbrain.ollama_client import is_available

    if not is_available():
        record("Qwen", "ollama", "SKIP", "Ollama down")
        return
    record("Qwen", "ollama", "OK")
    try:
        from autolinkingbrain.review_context import review_budget_chars

        review_budget_chars()
        record("Qwen", "review_budget", "OK")
    except Exception as exc:
        record("Qwen", "review_budget", "FAIL", str(exc))


def summary() -> int:
    section("SUMMARY")
    counts = {"OK": 0, "FAIL": 0, "SKIP": 0, "WARN": 0}
    for r in REPORT:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(f"OK={counts['OK']} FAIL={counts['FAIL']} WARN={counts['WARN']} SKIP={counts['SKIP']}")
    fails = [r for r in REPORT if r.status == "FAIL"]
    if fails:
        print("\nFailures:")
        for r in fails:
            print(f"  - [{r.area}] {r.name}: {r.detail}")
    out = ROOT / "scripts" / "manual_full_check_report.json"
    out.write_text(
        json.dumps([r.__dict__ for r in REPORT], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nReport: {out}")
    return 1 if fails else 0


def main() -> int:
    print(f"AutoLinkingBrain manual full check\nROOT={ROOT}\nPY={PY}\n")
    if not PY.is_file():
        print("ERROR: .venv missing — run python brain.py install")
        return 2
    check_imports()
    check_cli()
    check_mcp_direct()
    check_hooks()
    check_ollama_reviewer()
    check_viewer()
    return summary()


if __name__ == "__main__":
    raise SystemExit(main())
