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


def cmd_onboard(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.brain_config import init_default_config, load_config
    from autolinkingbrain.brain_install import run_onboard

    init_default_config(
        profile=args.profile,
        mcp_scope=args.mcp_scope,
        host_kind=args.host,
    )
    load_config(project_root=args.project_root or None)
    return run_onboard(
        host=args.host,
        mcp_scope=args.mcp_scope,
        project_root=args.project_root,
        profile=args.profile,
        pull_models=not args.no_pull_models,
        with_codegraph=not args.no_codegraph,
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
        return mcp_install(scope=args.scope, project_root=args.project_root, profile=args.profile, host=args.host)
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


def cmd_gc(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from autolinkingbrain.mem0_gc import audit_channel, list_duplicates, purge_candidates
    from autolinkingbrain.mem0_project_slug import resolve_project_slug

    db = _open_mem0()
    slug = args.channel.replace("project_", "") if args.channel.startswith("project_") else resolve_project_slug(
        project_root=args.project_root or os.getcwd()
    )
    uid = args.channel if args.channel.startswith("project_") or args.channel == "global_skills" else f"project_{slug}"

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
        result = purge_candidates(db, report, args.confirm_token, dry_run=dry)
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
    from autolinkingbrain.mem0_project_slug import resolve_project_slug
    from autolinkingbrain.project_analysis import evaluate_analysis_status, run_analysis_batch
    from autolinkingbrain.project_index_state import ProjectIndexState

    root = Path(args.project_root or os.getcwd()).resolve()
    slug = resolve_project_slug(project_root=str(root))
    db = _open_mem0()

    if args.analyze_command == "status":
        st = evaluate_analysis_status(db, project_root=root, project_slug=slug)
        if args.json:
            print(json.dumps({"state": st.state, "reason": st.reason, "entities": st.entity_count}, indent=2))
        else:
            print(st.format_block())
        return 0

    mode = args.analyze_command
    if mode == "auto":
        mode = "auto"

    def _add(text: str, uid: str) -> None:
        db.add(text, user_id=uid, infer=False)

    batch = args.batch_size
    total_processed = 0
    while True:
        result = run_analysis_batch(
            db,
            project_root=root,
            project_slug=slug,
            mode=mode if total_processed == 0 else "incremental",
            max_entities=batch,
            mem_add=_add,
        )
        total_processed += int(result.get("processed") or 0)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Batch: processed={result.get('processed')} remaining~={result.get('remaining_estimate')}")
        if result.get("next") == "done" or args.once:
            break
        if int(result.get("processed") or 0) == 0:
            break

    ProjectIndexState(root).export_markdown()
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
    p_on.add_argument("--profile", default="standard", choices=("minimal", "standard", "full"))
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

    p_an = sub.add_parser("analyze", help="Project analysis")
    p_an_sub = p_an.add_subparsers(dest="analyze_command", required=True)
    for name in ("status", "full", "incremental", "auto"):
        px = p_an_sub.add_parser(name)
        px.add_argument("--project-root", default="")
        px.add_argument("--batch-size", type=int, default=5)
        px.add_argument("--once", action="store_true", help="Single batch only")
        px.add_argument("--json", action="store_true")
        px.set_defaults(handler=cmd_analyze, analyze_command=name)

    p_fl = sub.add_parser("fleet", help="Fleet telemetry")
    p_fl_sub = p_fl.add_subparsers(dest="fleet_command", required=True)
    p_fls = p_fl_sub.add_parser("status")
    p_fls.set_defaults(handler=cmd_fleet, fleet_command="status")
    p_flp = p_fl_sub.add_parser("push")
    p_flp.add_argument("--url", default="")
    p_flp.add_argument("--token", default="")
    p_flp.add_argument("--project-root", default="")
    p_flp.set_defaults(handler=cmd_fleet, fleet_command="push")
