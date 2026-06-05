"""Migrate hook autolog rows from Chroma to .cursor/autolog.db."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def venv_python(root: Path | None = None) -> Path:
    base = root or ROOT
    name = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    return base / ".venv" / name


def ensure_mem0_importable(root: Path | None = None) -> None:
    """Re-exec with repo venv when system python lacks mem0ai."""
    try:
        import mem0  # noqa: F401
        return
    except ImportError:
        pass
    py = venv_python(root)
    if py.is_file():
        print(f"Using venv Python: {py}", file=sys.stderr)
        rc = subprocess.call([str(py), *sys.argv])
        raise SystemExit(rc)
    print(
        "mem0ai is not installed for this Python.\n"
        f"  Run: {venv_python(root)} -m pip install -r requirements.txt\n"
        "  Or:  python brain.py install\n"
        f"  Then: {py} scripts/migrate_autolog_to_sqlite.py ...",
        file=sys.stderr,
    )
    raise SystemExit(1)


def run_migrate(argv: list[str] | None = None) -> int:
    ensure_mem0_importable()

    from autolinkingbrain.autolog_store import import_from_mem0_row, resolve_db_path
    from autolinkingbrain.indexing_coverage import is_autolog_memory
    from autolinkingbrain.mem0_fetch import (
        _fetch_use_sqlite,
        discover_user_ids,
        discover_user_ids_sqlite,
        get_memory,
    )
    from autolinkingbrain.mem0_gc import audit_channel, fetch_all_rows, verify_confirm_token

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(ROOT), help="Repo root for autolog.db")
    parser.add_argument("--user-id", default="", help="Single Mem0 user_id (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no SQLite writes")
    parser.add_argument(
        "--purge-chroma",
        action="store_true",
        help="After migrate, purge autolog rows from Chroma (requires --confirm-token)",
    )
    parser.add_argument("--confirm-token", default="", help="From: python brain.py gc audit")
    args = parser.parse_args(argv)

    ws = Path(args.workspace).resolve()
    db_path = resolve_db_path(workspace_root=ws)
    if _fetch_use_sqlite():
        mem = None
        user_ids = (
            [args.user_id]
            if args.user_id
            else discover_user_ids_sqlite() or discover_user_ids()
        )
    else:
        mem = get_memory()
        user_ids = [args.user_id] if args.user_id else discover_user_ids()

    migrated = 0
    for uid in user_ids:
        rows = fetch_all_rows(mem, uid)
        for row in rows:
            body = str(row.get("memory") or "")
            if not is_autolog_memory(body):
                continue
            mid = str(row.get("id") or "")
            if not mid:
                continue
            if args.dry_run:
                migrated += 1
                continue
            import_from_mem0_row(
                memory_id=mid,
                user_id=uid,
                body=body,
                db_path=db_path,
            )
            migrated += 1

    print(f"autolog rows: {migrated} (dry_run={args.dry_run}) -> {db_path}")

    if args.purge_chroma:
        if not args.confirm_token:
            print(
                "ERROR: --purge-chroma requires --confirm-token from: python brain.py gc audit",
                file=sys.stderr,
            )
            return 1
        purged = 0
        for uid in user_ids:
            report = audit_channel(mem, uid)
            if not verify_confirm_token(report, args.confirm_token):
                print(f"ERROR: invalid confirm token for {uid}", file=sys.stderr)
                return 1
            for row in report.candidates:
                if row.category != "autolog":
                    continue
                try:
                    mem.delete(row.id)
                    purged += 1
                except Exception as exc:
                    print(f"  ! delete {row.id}: {exc}", file=sys.stderr)
            print(f"purged {purged} autolog rows from {uid}")
    return 0
