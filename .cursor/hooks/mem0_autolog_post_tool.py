"""
Cursor hook: postToolUse — compact log of agent file/search tool use into Mem0.

Stores one-line English facts (no Ollama) so retrieveChain can recall which files
were read/edited and what was searched. Complements afterAgentResponse (final reply).

Env: MEM0_TOOLLOG=1, MEM0_TOOLLOG_DEDUPE_SEC=120, MEM0_TOOLLOG_TARGET=project
Debug: MEM0_TOOLLOG_DEBUG=1 or file <repo>/.cursor/mem0_toollog_debug.on
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_LOG_DIR = _ROOT / ".cursor"
_LAST_RUN = _LOG_DIR / "mem0_toollog_last.txt"
_STDIN_DUMP = _LOG_DIR / "mem0_toollog_stdin.txt"
_GLOBAL_ID = "global_skills"
_DEBUG_MARKERS = ("mem0_toollog_debug.on",)

# Cursor tool_name values (normalized to lowercase keys).
_DEFAULT_TOOLS = frozenset(
    {
        "read",
        "write",
        "grep",
        "delete",
        "shell",
        "edit",
        "strreplace",
        "search_replace",
        "applypatch",
        "apply_patch",
        "glob",
        "list_dir",
        "listdir",
        "semanticsearch",
        "codebase_search",
        "search",
        "task",
        "create_file",
        "replace_string_in_file",
        "edit_file",
        "read_file",
        "run_terminal_cmd",
    }
)
_SKIP_TOOL_SUBSTR = (
    "autolinkingbrain",
    "codegraph",
    "checkprojecthealth",
    "retrievechain",
    "storeknowledge",
)


def _debug_enabled() -> bool:
    if os.environ.get("MEM0_TOOLLOG_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        return True
    for name in _DEBUG_MARKERS:
        if (_LOG_DIR / name).exists():
            return True
    return False


def _write_last(status: str, detail: str = "") -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now().isoformat()} status={status} {detail}\n"
        _LAST_RUN.write_text(line, encoding="utf-8")
    except Exception:
        pass
    try:
        from autolinkingbrain.brain_metrics import log_hook

        parts = detail.split("=", 1)
        project = parts[1].strip("'\"") if parts[0].strip() == "project" else ""
        log_hook("postToolUse", status, project=project, detail=detail[:200])
    except Exception:
        pass


def _enabled() -> bool:
    return os.environ.get("MEM0_TOOLLOG", "1").strip().lower() not in ("0", "false", "no")


def _allowed_tools() -> frozenset[str]:
    raw = os.environ.get("MEM0_TOOLLOG_TOOLS", "").strip()
    if not raw:
        return _DEFAULT_TOOLS
    return frozenset(t.strip().lower() for t in raw.split(",") if t.strip())


def _target_user_ids(project: str) -> list[str]:
    t = os.environ.get("MEM0_TOOLLOG_TARGET", "project").strip().lower()
    if t == "global":
        return [_GLOBAL_ID]
    if t == "both":
        return [f"project_{project}", _GLOBAL_ID]
    return [f"project_{project}"]


def _project_from_payload(data: dict, tool_input: dict | None = None) -> str:
    from autolinkingbrain.mem0_project_slug import resolve_slug_from_hook_payload

    return resolve_slug_from_hook_payload(data, tool_input)


def _dedupe_path(project: str) -> Path:
    safe = re.sub(r"[^\w\-.]", "_", project)[:80]
    return _LOG_DIR / f"mem0_toollog_dedupe_{safe}.json"


def _is_duplicate(project: str, payload: str) -> bool:
    window = int(os.environ.get("MEM0_TOOLLOG_DEDUPE_SEC", "120"))
    if window <= 0:
        return False
    key = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    path = _dedupe_path(project)
    try:
        if path.is_file():
            prev = json.loads(path.read_text(encoding="utf-8"))
            if prev.get("h") == key and time.time() - float(prev.get("t", 0)) < window:
                return True
    except Exception:
        pass
    return False


def _mark_written(project: str, payload: str) -> None:
    window = int(os.environ.get("MEM0_TOOLLOG_DEDUPE_SEC", "120"))
    if window <= 0:
        return
    key = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _dedupe_path(project).write_text(json.dumps({"h": key, "t": time.time()}), encoding="utf-8")
    except Exception:
        pass


def _normalize_tool_name(raw: str) -> str:
    name = (raw or "").strip()
    low = name.lower()
    if low.startswith("mcp:"):
        name = name.split(":", 1)[-1].strip()
        low = name.lower()
    return low.replace(" ", "_").replace("-", "_")


def _as_dict(val: object) -> dict:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _first_str(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _redact(text: str) -> str:
    if not text:
        return ""
    from autolinkingbrain.mem0_privacy import redact_secrets

    return redact_secrets(text.replace("\r\n", "\n").strip())


def _truncate(text: str, limit: int) -> str:
    t = _redact(text.replace("\r\n", "\n").strip())
    if len(t) <= limit:
        return t
    return t[: limit - 20] + " ... [truncated]"


def _extract_fields(data: dict) -> tuple[str, dict, str]:
    tool_name = _first_str(data, "tool_name", "toolName", "name")
    nested = data.get("tool_use") or data.get("toolUse") or data.get("tool") or {}
    if not tool_name and isinstance(nested, dict):
        tool_name = _first_str(nested, "name", "tool_name", "toolName")

    tool_input = (
        data.get("tool_input")
        or data.get("toolInput")
        or data.get("input")
        or data.get("arguments")
        or (nested.get("input") if isinstance(nested, dict) else None)
    )
    inp = _as_dict(tool_input)

    tool_output = (
        data.get("tool_output")
        or data.get("toolOutput")
        or data.get("tool_response")
        or data.get("toolResponse")
        or data.get("output")
        or data.get("result")
        or (nested.get("output") if isinstance(nested, dict) else None)
    )
    out = tool_output if isinstance(tool_output, str) else ""
    if not out and tool_output is not None:
        try:
            out = json.dumps(tool_output, ensure_ascii=False)[:800]
        except Exception:
            out = str(tool_output)[:800]
    return tool_name, inp, out


def _should_skip_tool(normalized: str) -> bool:
    if any(s in normalized for s in _SKIP_TOOL_SUBSTR):
        return True
    if normalized.startswith("mcp_"):
        return True
    return False


def _summarize_line(tool: str, inp: dict, out: str) -> str | None:
    t = _normalize_tool_name(tool)
    if _should_skip_tool(t):
        return None
    if t not in _allowed_tools():
        return None

    path = _first_str(
        inp,
        "path",
        "target_file",
        "file_path",
        "filePath",
        "relative_workspace_path",
        "targetFile",
    )
    pattern = _first_str(inp, "pattern", "glob_pattern", "globPattern", "search_term")
    query = _first_str(inp, "query", "search_term", "searchTerm", "recall_query")
    command = _first_str(inp, "command", "cmd")

    parts = [f"tool={tool or t}"]
    if path:
        parts.append(f"file={path}")
    if command:
        parts.append(f"cmd={_truncate(command, 160)}")
    if pattern:
        parts.append(f"pattern={_truncate(pattern, 120)}")
    if query and query != pattern:
        parts.append(f"query={_truncate(query, 120)}")

    out_limit = int(os.environ.get("MEM0_TOOLLOG_MAX_OUTPUT", "280"))
    if out and t in ("grep", "semanticsearch", "codebase_search", "glob", "list_dir", "search", "shell"):
        snippet = _truncate(out.replace("\n", " | "), out_limit)
        if snippet:
            parts.append(f"result={snippet}")

    if len(parts) <= 1:
        return None
    return " ".join(parts)


def main() -> None:
    if not _enabled():
        _write_last("disabled")
        print("{}")
        return

    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig")
    except Exception as e:
        _write_last("stdin_read_error", repr(e)[:120])
        print("{}")
        return

    if not raw.strip():
        _write_last("empty_stdin")
        print("{}")
        return

    if _debug_enabled():
        try:
            _STDIN_DUMP.write_text(raw, encoding="utf-8")
        except Exception:
            pass

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _write_last("json_error", repr(e)[:120])
        print("{}")
        return

    tool_name, tool_input, tool_output = _extract_fields(data)
    project = _project_from_payload(data, tool_input)
    summary = _summarize_line(tool_name, tool_input, tool_output)
    if not summary:
        _write_last(
            "skip_no_summary",
            f"project={project!r} tool={tool_name!r} cwd={data.get('cwd')!r} "
            f"roots={bool(data.get('workspace_roots'))}",
        )
        print("{}")
        return

    now = datetime.now().isoformat()
    cid = str(data.get("conversation_id") or "")[:12]
    line = f"[CURSOR] [TOOL_LOG] (Updated: {now}): conversation={cid} {summary}"

    if _is_duplicate(project, line):
        _write_last("skip_dedupe", f"project={project!r} tool={tool_name!r}")
        print("{}")
        return

    from autolinkingbrain.mem0_privacy import prepare_for_storage, should_block_write
    from autolinkingbrain.mem0_provenance import stamp_provenance

    safe_line, _ = prepare_for_storage(line)
    if should_block_write(safe_line):
        _write_last("skip_privacy_block", f"project={project!r} tool={tool_name!r}")
        print("{}")
        return

    tool_norm = _normalize_tool_name(tool_name)
    safe_line = stamp_provenance(
        safe_line,
        "hook:postToolUse",
        detail=f"tool={tool_norm or tool_name}",
    )

    stored_sqlite = False
    stored_mem0 = False
    uids: list[str] = []
    try:
        from autolinkingbrain.autolog_store import append_entry, writes_to_mem0, writes_to_sqlite

        if writes_to_sqlite():
            append_entry(
                project,
                "hook:postToolUse",
                safe_line,
                meta={"tool": tool_name, "conversation_id": cid},
                workspace_root=_ROOT,
            )
            stored_sqlite = True
        if writes_to_mem0():
            from mem0 import Memory

            from autolinkingbrain.mem0_settings import mem0_vector_config

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mem = Memory.from_config(config_dict=mem0_vector_config())
            uids = _target_user_ids(project)
            for uid in uids:
                mem.add(safe_line, user_id=uid, infer=False)
            try:
                from autolinkingbrain.mem0_hybrid_search import invalidate_channel_cache

                for uid in uids:
                    invalidate_channel_cache(uid)
            except Exception:
                pass
            try:
                from autolinkingbrain.mem0_kb_log import log_mem0

                log_mem0(
                    "write",
                    "hook.postToolUse.mem_add",
                    user_ids=uids,
                    tool=tool_name,
                    infer=False,
                )
            except Exception:
                pass
            stored_mem0 = True
        _mark_written(project, line)
        _write_last(
            "ok_wrote",
            f"project={project!r} sqlite={stored_sqlite} mem0={stored_mem0} "
            f"uids={uids} tool={tool_name!r}",
        )
    except Exception as e:
        _write_last("mem0_add_failed", f"project={project!r} err={repr(e)[:180]}")

    print("{}")


if __name__ == "__main__":
    main()
