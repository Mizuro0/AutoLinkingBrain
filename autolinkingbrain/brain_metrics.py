"""Offline metrics: brain_events.jsonl + aggregation for brain.py stats.

Events are local-only — never injected into MCP tool responses or agent context.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from autolinkingbrain.paths import REPO_ROOT

_DEFAULT_EVENTS = REPO_ROOT / ".cursor" / "brain_events.jsonl"
_LEGACY_KB = REPO_ROOT / ".cursor" / "mem0_kb_activity.log"

# Heuristic ROI (override via env).
_TOKENS_PER_MEMORY_HIT = int(os.environ.get("MEM0_METRICS_TOKENS_PER_HIT", "420"))
_TOKENS_PER_STORED_CHAR = float(os.environ.get("MEM0_METRICS_TOKENS_PER_STORED_CHAR", "0.35"))
_USD_PER_1M_TOKENS = float(os.environ.get("MEM0_METRICS_USD_PER_1M", "3.0"))


def events_path() -> Path:
    return Path(os.environ.get("MEM0_EVENTS_PATH", str(_DEFAULT_EVENTS))).expanduser().resolve()


def events_enabled() -> bool:
    return os.environ.get("MEM0_METRICS", "1").strip().lower() not in ("0", "false", "no")


def log_event(event: str, source: str, **fields: object) -> None:
    if not events_enabled():
        return
    try:
        from autolinkingbrain.brain_metrics_async import async_enabled, enqueue_event

        if async_enabled():
            enqueue_event(event, source, **fields)
            return
    except ImportError:
        pass
    path = events_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "source": source,
        }
        for k, v in fields.items():
            if v is not None:
                rec[k] = v
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_hook(hook: str, status: str, *, project: str = "", **fields: object) -> None:
    log_event(f"hook.{hook}", f"hook.{hook}", status=status, project=project, **fields)


def _parse_ts(raw: str | None) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _legacy_to_event(rec: dict) -> dict:
    op = rec.get("op")
    source = str(rec.get("source") or "")
    event = "mem.read" if op == "read" else "mem.write" if op == "write" else "mem.unknown"
    out = {
        "ts": rec.get("ts"),
        "event": event,
        "source": source,
        "_legacy": True,
    }
    for k, v in rec.items():
        if k not in ("ts", "op", "source"):
            out[k] = v
    return out


def _iter_file(path: Path) -> Iterator[dict]:
    if not path.is_file():
        return
    try:
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    yield rec
    except OSError:
        return


def iter_events(*, days: float = 7.0, since: datetime | None = None) -> Iterator[dict]:
    cutoff = since or (datetime.now(timezone.utc) - timedelta(days=max(0.01, days)))
    seen: set[str] = set()

    files: list[tuple[Path, bool]] = [(events_path(), False)]
    kb = kb_log_legacy_path()
    if kb.is_file() and kb.resolve() != events_path().resolve():
        files.append((kb, True))

    for path, force_legacy in files:
        for rec in _iter_file(path):
            if force_legacy or ("event" not in rec and "op" in rec):
                rec = _legacy_to_event(rec)
            ts = _parse_ts(str(rec.get("ts") or ""))
            if ts is None or ts < cutoff:
                continue
            key = json.dumps(rec, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            yield rec


def kb_log_legacy_path() -> Path:
    from autolinkingbrain.mem0_kb_log import kb_log_path

    return kb_log_path()


def aggregate(*, days: float = 7.0) -> dict:
    events = list(iter_events(days=days))
    return _aggregate_events(events, days=days)


def aggregate_for_viewer(*, days: float = 7.0, recent_limit: int = 80) -> dict:
    events = list(iter_events(days=days))
    report = _aggregate_events(events, days=days)
    report["daily"] = _daily_breakdown(events)
    report["recent"] = _recent_events(events, limit=recent_limit)
    report["hook_chart"] = _hook_chart_data(report.get("hook_status") or {})
    report["write_chart"] = _top_chart_data(report.get("write_by_source") or {}, limit=8)
    proot = os.environ.get("VIEWER_PROJECT_ROOT", "").strip()
    if proot:
        try:
            from autolinkingbrain.project_analysis import evaluate_analysis_status
            from autolinkingbrain.project_index_state import ProjectIndexState
            from mem0 import Memory
            from autolinkingbrain.mem0_settings import mem0_vector_config
            from autolinkingbrain.mem0_project_slug import resolve_project_slug

            slug = resolve_project_slug(project_root=proot)
            db = Memory.from_config(config_dict=mem0_vector_config())
            st = evaluate_analysis_status(db, project_root=proot, project_slug=slug)
            report["ops"] = {
                "analysis": st.format_block(),
                "project_index": str(ProjectIndexState(proot).md_path),
            }
        except Exception as exc:
            report["ops"] = {"error": str(exc)}
    report["metrics_tier"] = "local_viewer"
    return report


def _aggregate_events(events: list[dict], *, days: float) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(0.01, days))

    mem_reads = 0
    mem_writes = 0
    read_rows = 0
    stored_chars = 0
    read_by_source: Counter[str] = Counter()
    write_by_source: Counter[str] = Counter()
    hook_status: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    mcp_hits = 0
    hybrid_reads = 0

    for rec in events:
        event = str(rec.get("event") or "")
        source = str(rec.get("source") or "")
        status = str(rec.get("status") or "")

        if event == "mem.read":
            mem_reads += 1
            rows = int(rec.get("rows") or rec.get("hits") or 0)
            read_rows += rows
            read_by_source[source] += 1
            if source.startswith("mcp.") and rows > 0:
                mcp_hits += 1
            if rec.get("hybrid"):
                hybrid_reads += 1
        elif event == "mem.write":
            mem_writes += 1
            stored_chars += int(rec.get("stored_chars") or 0)
            write_by_source[source] += 1
        elif event.startswith("hook."):
            hook_status[f"{event}:{status or 'unknown'}"] += 1
            if status in ("mem0_add_failed", "stdin_read_error", "json_error"):
                errors[status] += 1
        elif event == "mcp.tool":
            if status == "error":
                errors[f"mcp:{rec.get('tool', '?')}"] += 1

    tokens_from_reads = 0
    for rec in events:
        if str(rec.get("event") or "") != "mem.read":
            continue
        source = str(rec.get("source") or "")
        if source.startswith("viewer."):
            continue
        rows = int(rec.get("rows") or rec.get("hits") or 0)
        if rows <= 0:
            continue
        if source.startswith("mcp.") or source.startswith("hook.sessionStart"):
            tokens_from_reads += rows * _TOKENS_PER_MEMORY_HIT
    tokens_from_stores = int(stored_chars * _TOKENS_PER_STORED_CHAR)
    tokens_saved_est = tokens_from_reads + tokens_from_stores
    usd_saved_est = round(tokens_saved_est / 1_000_000 * _USD_PER_1M_TOKENS, 4)

    codegraph = _codegraph_summary()
    mem0_channels = _mem0_channel_summary()

    return {
        "period_days": days,
        "since": cutoff.isoformat(),
        "until": now.isoformat(),
        "event_count": len(events),
        "mem_reads": mem_reads,
        "mem_writes": mem_writes,
        "read_rows_total": read_rows,
        "stored_chars_total": stored_chars,
        "mcp_search_hits": mcp_hits,
        "hybrid_reads": hybrid_reads,
        "read_by_source": dict(read_by_source.most_common(15)),
        "write_by_source": dict(write_by_source.most_common(15)),
        "hook_status": dict(hook_status.most_common(20)),
        "errors": dict(errors),
        "roi": {
            "tokens_saved_estimate": tokens_saved_est,
            "usd_saved_estimate": usd_saved_est,
            "tokens_per_hit": _TOKENS_PER_MEMORY_HIT,
            "note": "heuristic — Cursor does not expose real token bills to MCP",
        },
        "codegraph": codegraph,
        "mem0": mem0_channels,
        "events_path": str(events_path()),
    }


def _daily_breakdown(events: list[dict]) -> list[dict]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"reads": 0, "writes": 0, "hooks": 0})
    for rec in events:
        ts = _parse_ts(str(rec.get("ts") or ""))
        if ts is None:
            continue
        day = ts.strftime("%Y-%m-%d")
        event = str(rec.get("event") or "")
        if event == "mem.read":
            buckets[day]["reads"] += 1
        elif event == "mem.write":
            buckets[day]["writes"] += 1
        elif event.startswith("hook."):
            buckets[day]["hooks"] += 1
    return [{"date": d, **buckets[d]} for d in sorted(buckets)]


def _event_summary(rec: dict) -> str:
    event = str(rec.get("event") or "")
    source = str(rec.get("source") or "")
    status = str(rec.get("status") or "")
    if event == "mem.read":
        rows = rec.get("rows") or rec.get("hits")
        extra = f" rows={rows}" if rows is not None else ""
        return f"read {source}{extra}"
    if event == "mem.write":
        chars = rec.get("stored_chars")
        tool = rec.get("tool")
        parts = [f"write {source}"]
        if chars:
            parts.append(f"{chars} chars")
        if tool:
            parts.append(f"tool={tool}")
        return " · ".join(parts)
    if event.startswith("hook."):
        proj = rec.get("project") or ""
        detail = str(rec.get("detail") or rec.get("extra") or "")[:80]
        base = f"{event.replace('hook.', '')} → {status or '?'}"
        if proj:
            base += f" ({proj})"
        if detail:
            base += f" {detail}"
        return base
    return f"{event} {source} {status}".strip()


def _event_kind(rec: dict) -> str:
    event = str(rec.get("event") or "")
    status = str(rec.get("status") or "")
    if status in ("mem0_add_failed", "stdin_read_error", "json_error") or status.startswith("error"):
        return "error"
    if event == "mem.read":
        return "read"
    if event == "mem.write":
        return "write"
    if event.startswith("hook."):
        if status.startswith("skip") or status in ("disabled", "empty_stdin", "skip_no_summary"):
            return "skip"
        if status.startswith("ok"):
            return "ok"
        return "hook"
    return "other"


def _recent_events(events: list[dict], *, limit: int) -> list[dict]:
    sorted_ev = sorted(events, key=lambda r: str(r.get("ts") or ""), reverse=True)
    out: list[dict] = []
    for rec in sorted_ev[: max(1, limit)]:
        out.append(
            {
                "ts": rec.get("ts"),
                "event": rec.get("event"),
                "source": rec.get("source"),
                "status": rec.get("status"),
                "kind": _event_kind(rec),
                "summary": _event_summary(rec),
            }
        )
    return out


def _hook_chart_data(hook_status: dict[str, int]) -> list[dict]:
    buckets: Counter[str] = Counter()
    for key, count in hook_status.items():
        status = key.split(":", 1)[-1] if ":" in key else key
        if status.startswith("ok"):
            buckets["ok"] += count
        elif status.startswith("skip"):
            buckets["skip"] += count
        elif "failed" in status or "error" in status:
            buckets["error"] += count
        else:
            buckets["other"] += count
    labels = {"ok": "OK", "skip": "Skip", "error": "Error", "other": "Other"}
    return [{"label": labels.get(k, k), "key": k, "count": v} for k, v in buckets.items() if v]


def _top_chart_data(data: dict[str, int], *, limit: int) -> list[dict]:
    items = sorted(data.items(), key=lambda x: -x[1])[:limit]
    return [{"label": k.replace("hook.", "").replace("mcp.", ""), "count": v} for k, v in items]


def _codegraph_summary() -> dict:
    try:
        from autolinkingbrain.codegraph_init import collect_repo_paths, codegraph_bin, repo_has_index

        if not codegraph_bin():
            return {"available": False, "indexed": 0, "total": 0}
        repos = collect_repo_paths()
        indexed = sum(1 for r in repos if repo_has_index(r))
        return {"available": True, "indexed": indexed, "total": len(repos)}
    except Exception as exc:
        return {"available": False, "error": str(exc)[:120]}


def _mem0_channel_summary() -> dict:
    try:
        import chromadb
        from chromadb.config import Settings

        from autolinkingbrain.mem0_settings import CHROMA_COLLECTION, chroma_path_resolved

        client = chromadb.PersistentClient(
            path=str(chroma_path_resolved()),
            settings=Settings(anonymized_telemetry=False),
        )
        col = client.get_collection(CHROMA_COLLECTION)
        total = col.count()
        return {"collection": CHROMA_COLLECTION, "total_memories": total}
    except Exception as exc:
        return {"error": str(exc)[:120]}


def format_report(report: dict) -> str:
    roi = report.get("roi") or {}
    cg = report.get("codegraph") or {}
    mem0 = report.get("mem0") or {}
    lines = [
        f"AutoLinkingBrain Stats ({report.get('period_days', '?')}d)",
        f"  events logged:     {report.get('event_count', 0)}",
        f"  log file:            {report.get('events_path', '')}",
        "",
        "Mem0 activity:",
        f"  reads:               {report.get('mem_reads', 0)}  (rows returned: {report.get('read_rows_total', 0)})",
        f"  writes:              {report.get('mem_writes', 0)}  (chars stored: {report.get('stored_chars_total', 0)})",
        f"  MCP search hits:     {report.get('mcp_search_hits', 0)}",
        f"  hybrid reads:        {report.get('hybrid_reads', 0)}",
        "",
        "ROI (estimate):",
        f"  tokens saved:        ~{roi.get('tokens_saved_estimate', 0):,}",
        f"  USD saved:           ~${roi.get('usd_saved_estimate', 0)}",
        f"  ({roi.get('note', '')})",
    ]

    if cg.get("available"):
        lines.extend(
            [
                "",
                "CodeGraph:",
                f"  indexed repos:       {cg.get('indexed', 0)}/{cg.get('total', 0)}",
            ]
        )
    elif cg.get("available") is False:
        lines.extend(["", "CodeGraph:             not on PATH"])

    if mem0.get("total_memories") is not None:
        lines.extend(
            [
                "",
                "Mem0 store:",
                f"  total memories:      {mem0.get('total_memories', 0)}",
            ]
        )

    hook_status = report.get("hook_status") or {}
    if hook_status:
        lines.append("")
        lines.append("Hooks (top):")
        for key, count in sorted(hook_status.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  {key}: {count}")

    read_src = report.get("read_by_source") or {}
    if read_src:
        lines.append("")
        lines.append("Read sources (top):")
        for src, count in read_src.items():
            lines.append(f"  {src}: {count}")

    errors = report.get("errors") or {}
    if errors:
        lines.append("")
        lines.append("Errors:")
        for err, count in errors.items():
            lines.append(f"  {err}: {count}")

    return "\n".join(lines)
