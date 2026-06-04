"""CLI commands: onboard, doctor, mcp, health, context, gc, analyze, fleet."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

os.environ.setdefault("MEM0_FETCH_SQLITE", "1")


def cmd_onboard(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.brain_config import init_default_config, load_config
    from autolinkingbrain.brain_install import run_onboard
    from autolinkingbrain.local_install import resolve_mcp_install_kwargs

    kw = resolve_mcp_install_kwargs(
        profile=args.profile,
        scope=args.mcp_scope,
        project_root=args.project_root,
        host=args.host,
        with_codegraph=None if args.no_codegraph else None,
    )
    init_default_config(
        profile=kw["profile"],
        mcp_scope=kw["scope"],
        host_kind=kw["host"],
    )
    load_config(project_root=args.project_root or None)
    return run_onboard(
        host=kw["host"],
        mcp_scope=kw["scope"],
        project_root=kw["project_root"],
        profile=kw["profile"],
        pull_models=not args.no_pull_models,
        with_codegraph=kw["with_codegraph"],
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.brain_install import run_doctor

    report = run_doctor(project_root=args.project_root, as_json=args.json)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report.get("checks", []):
            mark = {"ok": "✓", "warn": "⚠", "fail": "✗"}.get(check["status"], "?")
            print(f"  {mark} {check['name']}: {check.get('detail', '')}")
        print(f"\nOverall: {report.get('overall', 'unknown')}")
    return 0 if report.get("overall") == "ok" else 1


def cmd_mcp(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.brain_install import mcp_install, mcp_status, mcp_uninstall

    if args.mcp_command == "status":
        st = mcp_status(scope=args.scope, project_root=args.project_root, host=args.host)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    if args.mcp_command == "install":
        from autolinkingbrain.local_install import resolve_mcp_install_kwargs

        kw = resolve_mcp_install_kwargs(
            profile=getattr(args, "profile", None),
            scope=getattr(args, "scope", None),
            project_root=getattr(args, "project_root", None),
            host=getattr(args, "host", None),
        )
        return mcp_install(**kw)
    if args.mcp_command == "uninstall":
        return mcp_uninstall(scope=args.scope, project_root=args.project_root, host=args.host)
    return 1


def cmd_health(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from mem0 import Memory

    from autolinkingbrain.mcp_context import McpContext
    from autolinkingbrain.mem0_project_slug import resolve_project_slug
    from autolinkingbrain.mem0_settings import mem0_vector_config

    slug = resolve_project_slug(project_root=args.project_root or os.getcwd())
    db = Memory.from_config(config_dict=mem0_vector_config())
    ctx = McpContext(db=db)
    body = ctx.build_check_project_health_body(slug, f"project_{slug}")
    print(body)
    return 0


def cmd_context_pack(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from mem0 import Memory

    from autolinkingbrain.mcp_context import McpContext
    from autolinkingbrain.mem0_settings import mem0_vector_config

    db = Memory.from_config(config_dict=mem0_vector_config())
    ctx = McpContext(db=db)
    q = args.query or "project overview architecture stack"
    body = ctx.retrieve_chain_body(q, project_id=ctx.get_project_id(project_root=args.project_root))
    print(body)
    return 0


def _open_mem0():
    from mem0 import Memory

    from autolinkingbrain.mem0_settings import mem0_vector_config

    return Memory.from_config(config_dict=mem0_vector_config())


def cmd_migrate_autolog(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.migrate_autolog import run_migrate

    argv: list[str] = []
    if getattr(args, "workspace", ""):
        argv.extend(["--workspace", args.workspace])
    if getattr(args, "user_id", ""):
        argv.extend(["--user-id", args.user_id])
    if getattr(args, "dry_run", False):
        argv.append("--dry-run")
    if getattr(args, "purge_chroma", False):
        argv.append("--purge-chroma")
    if getattr(args, "confirm_token", ""):
        argv.extend(["--confirm-token", args.confirm_token])
    return run_migrate(argv)


def cmd_gc(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.mem0_gc import audit_channel, list_duplicates, purge_candidates
    from autolinkingbrain.mem0_project_slug import resolve_project_slug

    slug = args.channel.replace("project_", "") if args.channel.startswith("project_") else resolve_project_slug(
        project_root=args.project_root or os.getcwd()
    )
    uid = args.channel if args.channel.startswith("project_") or args.channel == "global_skills" else f"project_{slug}"

    if args.gc_command == "purge-indexing":
        import warnings

        from autolinkingbrain.mem0_gc import purge_indexing_logs

        warnings.filterwarnings("ignore", category=DeprecationWarning)

        def _progress(msg: str) -> None:
            print(msg, file=sys.stderr, flush=True)

        dry = not getattr(args, "apply", False)
        target_uid = uid if args.channel else None
        mode = "dry-run" if dry else "apply"
        _progress(f"purge-indexing: {mode} (progress on stderr; result JSON on stdout)")
        result = purge_indexing_logs(db=None, user_id=target_uid, dry_run=dry, log=_progress)
        print(
            json.dumps(
                {
                    "dry_run": result.dry_run,
                    "deleted": result.deleted,
                    "skipped": result.skipped,
                    "errors": result.errors,
                },
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0 if not result.errors else 1

    from autolinkingbrain.mem0_fetch import _fetch_use_sqlite, delete_memory_sqlite

    db = None if _fetch_use_sqlite() else _open_mem0()
    _delete_fn = delete_memory_sqlite if _fetch_use_sqlite() else None

    if args.gc_command == "audit":
        report = audit_channel(db, uid)
        if args.json:
            print(json.dumps({
                "user_id": report.user_id,
                "total": report.total,
                "by_category": report.by_category,
                "confirm_token": report.confirm_token,
            }, indent=2))
        else:
            print(report.format_markdown())
        return 0

    if args.gc_command == "purge":
        report = audit_channel(db, uid)
        dry = args.dry_run and not getattr(args, "apply", False)
        result = purge_candidates(
            db, report, args.confirm_token, dry_run=dry, delete_fn=_delete_fn
        )
        print(json.dumps({
            "dry_run": result.dry_run,
            "deleted": result.deleted,
            "errors": result.errors,
        }, indent=2))
        return 0 if not result.errors else 1

    if args.gc_command == "dedupe-exact":
        groups = list_duplicates(db, uid)
        print(f"Duplicate groups: {len(groups)}")
        if args.apply:
            deleted = 0
            for g in groups:
                for mid in g.ids[1:]:
                    try:
                        if _delete_fn:
                            _delete_fn(mid)
                        elif db is not None:
                            db.delete(mid)
                        deleted += 1
                    except Exception:
                        pass
            print(f"Deleted duplicates: {deleted}")
        else:
            for g in groups[:20]:
                print(f"  {g.fingerprint}: {len(g.ids)} ids")
        return 0

    return 1


def cmd_analyze(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("MEM0_FETCH_SQLITE", "1")

    if args.analyze_command == "sync":
        from autolinkingbrain.project_sync import sync_discovered_projects

        extra: list[str] = []
        raw_paths = (getattr(args, "paths", "") or "").strip()
        if raw_paths:
            extra = [p.strip() for p in raw_paths.replace("\n", ";").split(";") if p.strip()]
        out = sync_discovered_projects(
            extra_paths=extra,
            mode=getattr(args, "mode", "auto"),
            batch_size=args.batch_size,
            index_only=not getattr(args, "with_mem0", False),
            use_subprocess=not getattr(args, "in_process", False),
        )
        print(json.dumps(out, ensure_ascii=False, indent=2 if args.json else None))
        return 0 if out.get("ok") else 1

    from autolinkingbrain.mem0_project_slug import resolve_project_slug
    from autolinkingbrain.project_analysis import evaluate_analysis_status, run_analysis_batch
    from autolinkingbrain.project_index_state import ProjectIndexState

    root = Path(args.project_root or os.getcwd()).resolve()
    slug = resolve_project_slug(project_root=str(root))
    index_only = getattr(args, "index_only", False)
    db = None if index_only else _open_mem0()

    if args.analyze_command == "status":
        st = evaluate_analysis_status(db, project_root=root, project_slug=slug)
        if args.json:
            print(json.dumps({"state": st.state, "reason": st.reason, "entities": st.entity_count}, indent=2))
        else:
            print(st.format_block())
        return 0

    mode = args.analyze_command
    mem_add = None
    if not index_only and db is not None:

        def _add(text: str, uid: str) -> None:
            db.add(text, user_id=uid, infer=False)

        mem_add = _add

    batch = args.batch_size
    total_processed = 0
    batches = 0
    last: dict = {}
    while True:
        batches += 1
        last = run_analysis_batch(
            db,
            project_root=root,
            project_slug=slug,
            mode=mode if batches == 1 else "incremental",
            max_entities=batch,
            mem_add=mem_add,
        )
        total_processed += int(last.get("processed") or 0)
        if args.json and not getattr(args, "until_done", False):
            print(json.dumps(last, indent=2))
        elif not args.json:
            print(
                f"Batch: processed={last.get('processed')} "
                f"remaining~={last.get('remaining_estimate')} next={last.get('next')}"
            )
        if last.get("next") == "done" or args.once:
            break
        if int(last.get("processed") or 0) == 0:
            break
        if not getattr(args, "until_done", False):
            break

    ProjectIndexState(root).export_markdown()
    if getattr(args, "until_done", False) and args.json:
        st = evaluate_analysis_status(db, project_root=root, project_slug=slug)
        print(
            json.dumps(
                {
                    "ok": last.get("next") == "done",
                    "project_root": str(root),
                    "project_slug": slug,
                    "batches": batches,
                    "entities_processed": total_processed,
                    "last_batch": last,
                    "analysis_status": st.format_block(),
                    "index_only": index_only,
                },
                ensure_ascii=False,
            )
        )
    return 0


def cmd_fleet(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.brain_config import load_config
    from autolinkingbrain.brain_fleet_client import build_snapshot, fleet_enabled, push_snapshot
    from autolinkingbrain.mem0_project_slug import resolve_project_slug

    cfg = load_config()
    if args.fleet_command == "status":
        print(json.dumps({
            "enabled": fleet_enabled() or cfg.fleet_enabled,
            "url": cfg.fleet_url,
            "has_token": bool(cfg.fleet_token),
        }, indent=2))
        return 0
    if args.fleet_command == "push":
        url = args.url or cfg.fleet_url
        token = args.token or cfg.fleet_token
        if not url or not token:
            print("Fleet URL and install token required", file=sys.stderr)
            return 1
        slug = resolve_project_slug(project_root=args.project_root or os.getcwd())
        result = push_snapshot(url=url, token=token, project_slug=slug)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    return 1


def add_cli_parsers(sub: argparse._SubParsersAction) -> None:
    p_on = sub.add_parser("onboard", help="One-command setup")
    p_on.add_argument("--host", default="cursor", choices=("auto", "cursor", "vscode", "cli", "ci"))
    p_on.add_argument("--mcp-scope", default="global", choices=("global", "project"))
    p_on.add_argument("--project-root", default="")
    p_on.add_argument(
        "--profile",
        default=None,
        choices=("minimal", "standard", "full"),
        help="MCP profile (default: config/local/install.yaml or standard)",
    )
    p_on.add_argument("--no-pull-models", action="store_true")
    p_on.add_argument("--no-codegraph", action="store_true")
    p_on.set_defaults(handler=cmd_onboard)

    p_doc = sub.add_parser("doctor", help="Diagnostics")
    p_doc.add_argument("--project-root", default="")
    p_doc.add_argument("--json", action="store_true")
    p_doc.set_defaults(handler=cmd_doctor)

    p_mcp = sub.add_parser("mcp", help="MCP install/status")
    p_mcp_sub = p_mcp.add_subparsers(dest="mcp_command", required=True)
    for name in ("status", "install", "uninstall"):
        px = p_mcp_sub.add_parser(name)
        px.add_argument("--scope", default="global", choices=("global", "project"))
        px.add_argument("--project-root", default="")
        if name == "install":
            px.add_argument(
                "--profile",
                default=None,
                choices=("minimal", "standard", "full"),
                help="Override config/local/install.yaml",
            )
        else:
            px.add_argument("--profile", default="standard", choices=("minimal", "standard", "full"))
        px.add_argument("--host", default="cursor")
        px.set_defaults(handler=cmd_mcp, mcp_command=name)

    p_h = sub.add_parser("health", help="checkProjectHealth CLI fallback")
    p_h.add_argument("--project-root", default="")
    p_h.set_defaults(handler=cmd_health)

    p_c = sub.add_parser("context", help="Context pack")
    p_c_sub = p_c.add_subparsers(dest="context_command", required=True)
    p_cp = p_c_sub.add_parser("pack")
    p_cp.add_argument("--query", default="")
    p_cp.add_argument("--project-root", default="")
    p_cp.set_defaults(handler=cmd_context_pack)

    p_mig = sub.add_parser(
        "migrate-autolog",
        help="Copy hook autolog from Chroma to .cursor/autolog.db (uses venv)",
    )
    p_mig.add_argument("--workspace", default="")
    p_mig.add_argument("--user-id", default="")
    p_mig.add_argument("--dry-run", action="store_true")
    p_mig.add_argument("--purge-chroma", action="store_true")
    p_mig.add_argument("--confirm-token", default="")
    p_mig.set_defaults(handler=cmd_migrate_autolog)

    p_gc = sub.add_parser("gc", help="Knowledge GC")
    p_gc_sub = p_gc.add_subparsers(dest="gc_command", required=True)
    p_gca = p_gc_sub.add_parser("audit")
    p_gca.add_argument("--channel", default="")
    p_gca.add_argument("--project-root", default="")
    p_gca.add_argument("--json", action="store_true")
    p_gca.set_defaults(handler=cmd_gc, gc_command="audit")
    p_gcp = p_gc_sub.add_parser("purge")
    p_gcp.add_argument("--confirm-token", required=True)
    p_gcp.add_argument("--dry-run", action="store_true", default=True)
    p_gcp.add_argument("--apply", action="store_true", help="Actually delete (disables dry-run)")
    p_gcp.add_argument("--channel", default="")
    p_gcp.add_argument("--project-root", default="")
    p_gcp.set_defaults(handler=cmd_gc, gc_command="purge")
    p_gcd = p_gc_sub.add_parser("dedupe-exact")
    p_gcd.add_argument("--apply", action="store_true")
    p_gcd.add_argument("--channel", default="")
    p_gcd.add_argument("--project-root", default="")
    p_gcd.set_defaults(handler=cmd_gc, gc_command="dedupe-exact")
    p_gip = p_gc_sub.add_parser(
        "purge-indexing",
        help="Remove per-file 'Indexed source' logs from project_* channels",
    )
    p_gip.add_argument("--apply", action="store_true", help="Actually delete (default dry-run)")
    p_gip.add_argument("--channel", default="", help="Optional project_<slug> channel; default all projects")
    p_gip.add_argument("--project-root", default="")
    p_gip.set_defaults(handler=cmd_gc, gc_command="purge-indexing")

    p_an = sub.add_parser("analyze", help="Project analysis")
    p_an_sub = p_an.add_subparsers(dest="analyze_command", required=True)
    for name in ("status", "full", "incremental", "auto"):
        px = p_an_sub.add_parser(name)
        px.add_argument("--project-root", default="")
        px.add_argument("--batch-size", type=int, default=5)
        px.add_argument("--once", action="store_true", help="Single batch only")
        px.add_argument("--until-done", action="store_true", help="Run batches until next=done")
        px.add_argument(
            "--index-only",
            action="store_true",
            help="Only .brain/project_index.db (no Mem0 signal writes)",
        )
        px.add_argument("--json", action="store_true")
        px.set_defaults(handler=cmd_analyze, analyze_command=name)
    p_sync = p_an_sub.add_parser(
        "sync",
        help="Index all discovered repos until done (set-and-forget; safe while MCP runs)",
    )
    p_sync.add_argument(
        "--paths",
        default="",
        help="Extra repo roots (; separated), e.g. D:/codes/backend;D:/codes/altey",
    )
    p_sync.add_argument("--mode", default="auto", choices=("auto", "full", "incremental"))
    p_sync.add_argument("--batch-size", type=int, default=5)
    p_sync.add_argument(
        "--with-mem0",
        action="store_true",
        help="Also emit REST/SERVICE signals to Mem0 (default: index DB only)",
    )
    p_sync.add_argument(
        "--in-process",
        action="store_true",
        help="Do not spawn subprocess per repo (not recommended on Windows)",
    )
    p_sync.add_argument("--json", action="store_true")
    p_sync.set_defaults(handler=cmd_analyze, analyze_command="sync")

    p_fl = sub.add_parser("fleet", help="Fleet telemetry")
    p_fl_sub = p_fl.add_subparsers(dest="fleet_command", required=True)
    p_fls = p_fl_sub.add_parser("status")
    p_fls.set_defaults(handler=cmd_fleet, fleet_command="status")
    p_flp = p_fl_sub.add_parser("push")
    p_flp.add_argument("--url", default="")
    p_flp.add_argument("--token", default="")
    p_flp.add_argument("--project-root", default="")
    p_flp.set_defaults(handler=cmd_fleet, fleet_command="push")
