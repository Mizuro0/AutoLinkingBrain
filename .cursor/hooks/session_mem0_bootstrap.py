"""
sessionStart: подмешивает в начало сессии краткий снимок уже сохранённых фактов из Mem0/Chroma.

Вызывается при создании новой сессии Composer (Agent / Ask / Edit), не при каждом открытии папки в Explorer.
Запись *новых* фактов в граф по-прежнему делается агентом (MCP) или хуком afterAgentResponse — здесь только чтение.
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_OFF = os.environ.get("MEM0_SESSION_BOOTSTRAP", "1").strip().lower() in ("0", "false", "no")
_MAX_TOTAL = int(os.environ.get("MEM0_SESSION_BOOTSTRAP_MAX_CHARS", "10000"))
_MAX_PROJECT = int(os.environ.get("MEM0_SESSION_BOOTSTRAP_PROJECT_MEMORIES", "25"))
_MAX_GLOBAL = int(os.environ.get("MEM0_SESSION_BOOTSTRAP_GLOBAL_MEMORIES", "10"))
_GLOBAL_ID = "global_skills"


def _rows(raw: object) -> list[dict]:
    if isinstance(raw, dict):
        return list(raw.get("results") or [])
    if isinstance(raw, list):
        return list(raw)
    return []


def _sort_key(row: dict) -> str:
    return (row.get("updated_at") or row.get("created_at") or "") or ""


def _format_block(title: str, memories: list[dict]) -> str:
    line_max = int(os.environ.get("MEM0_SESSION_BOOTSTRAP_LINE_CHARS", "480"))
    line_max = max(120, min(line_max, 1000))
    if not memories:
        return f"### {title}\n(none)\n"
    lines = [f"### {title}", ""]
    for i, row in enumerate(memories, 1):
        text = (row.get("memory") or "").strip().replace("\r\n", "\n")
        if not text:
            continue
        one = text[:line_max] + ("…" if len(text) > line_max else "")
        lines.append(f"{i}. {one}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    try:
        raw = sys.stdin.buffer.read()
        if not raw.strip():
            print("{}")
            return
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception:
        print("{}")
        return

    try:
        from autolinkingbrain.cursor_agent import sync_global_agent_assets

        sync_global_agent_assets(force=False)
    except Exception:
        pass

    _protocol_off = os.environ.get("MEM0_SESSION_PROTOCOL", "1").strip().lower() in ("0", "false", "no")
    protocol = ""
    if not _protocol_off:
        try:
            from autolinkingbrain.cursor_agent import compile_always_apply_rules_context

            protocol = compile_always_apply_rules_context(
                max_chars=int(os.environ.get("MEM0_SESSION_PROTOCOL_MAX_CHARS", "4500")),
            )
        except Exception:
            protocol = ""

    if _OFF:
        print("{}")
        return

    roots = data.get("workspace_roots") or []
    cwd = str(data.get("cwd") or "")
    from autolinkingbrain.mem0_project_slug import discover_project_slugs_for_workspace

    slugs = discover_project_slugs_for_workspace(
        workspace_roots=roots if isinstance(roots, list) else None,
        cwd=cwd or None,
    )
    if not slugs:
        if protocol:
            out = {"additional_context": protocol}
            print(json.dumps(out, ensure_ascii=False))
        else:
            print("{}")
        return

    per_slug = max(4, _MAX_PROJECT // max(1, len(slugs)))

    try:
        from mem0 import Memory

        from autolinkingbrain.mem0_settings import mem0_vector_config

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mem = Memory.from_config(config_dict=mem0_vector_config())

        proj_rows: list[dict] = []
        for slug in slugs:
            project_uid = f"project_{slug}"
            raw_p = mem.get_all(filters={"user_id": project_uid}, top_k=max(per_slug * 2, 40))
            try:
                from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0

                log_mem0(
                    "read",
                    "hook.sessionStart.get_all",
                    user_id=project_uid,
                    top_k=max(per_slug * 2, 40),
                    rows=count_get_all_rows(raw_p),
                )
            except Exception:
                pass
            proj_rows.extend(sorted(_rows(raw_p), key=_sort_key, reverse=True)[:per_slug])

        raw_g = mem.get_all(filters={"user_id": _GLOBAL_ID}, top_k=max(_MAX_GLOBAL * 2, 28))
        try:
            from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0

            log_mem0(
                "read",
                "hook.sessionStart.get_all",
                user_id=_GLOBAL_ID,
                top_k=max(_MAX_GLOBAL * 2, 28),
                rows=count_get_all_rows(raw_g),
            )
        except Exception:
            pass
        glob_rows = sorted(_rows(raw_g), key=_sort_key, reverse=True)[:_MAX_GLOBAL]

        slug_label = ", ".join(f"`{s}`" for s in slugs)
        header = (
            "## Mem0 bootstrap (existing memories)\n\n"
            f"Workspace slugs: {slug_label} — project channels `project_<slug>`, "
            f"global channel `{_GLOBAL_ID}`.\n"
            "These lines are **already in the vector DB**; for live search use MCP `retrieveChain` / `checkProjectHealth`.\n\n"
        )
        body = ""
        if protocol:
            body = protocol.rstrip() + "\n\n---\n\n"
        body += header + _format_block(f"Project channels ({slug_label})", proj_rows)
        body += _format_block(f"Global channel ({_GLOBAL_ID})", glob_rows)
        if len(body) > _MAX_TOTAL:
            body = body[: _MAX_TOTAL - 80] + "\n\n… [Mem0 bootstrap truncated]\n"

        out = {"additional_context": body}
        print(json.dumps(out, ensure_ascii=False))
    except Exception:
        # fail-open: не ломаем старт сессии
        print("{}")


if __name__ == "__main__":
    main()
