"""Build bounded context pack for local-model code review."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from autolinkingbrain.codegraph_init import codegraph_bin
from autolinkingbrain.mcp_context import McpContext

_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_DIFF_FILE_RE2 = re.compile(r"^diff --git a/.+ b/(.+)$", re.MULTILINE)


def default_max_chars() -> int:
    return max(4000, int(os.environ.get("OLLAMA_REVIEW_MAX_CHARS", "24000")))


def review_budget_chars() -> dict[str, int]:
    total = default_max_chars()
    return {
        "total_max_chars": total,
        "approx_tokens": total // 3,
        "recommended_diff_chars": int(total * 0.55),
    }


def parse_changed_files(diff_text: str) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for pat in (_DIFF_FILE_RE, _DIFF_FILE_RE2):
        for m in pat.finditer(diff_text or ""):
            path = (m.group(1) or "").strip()
            if path and path != "/dev/null" and path not in seen:
                seen.add(path)
                files.append(path)
    return files


def truncate_section(text: str, max_chars: int, label: str) -> str:
    body = (text or "").strip()
    if max_chars <= 0 or len(body) <= max_chars:
        return body
    return body[: max_chars - 40] + f"\n… [{label} truncated]"


def truncate_diff_by_files(diff_text: str, max_chars: int) -> str:
    diff = diff_text or ""
    if len(diff) <= max_chars:
        return diff
    files = parse_changed_files(diff)
    if not files:
        return truncate_section(diff, max_chars, "diff")
    parts: list[str] = []
    used = 0
    for fp in files:
        chunk_re = re.compile(
            rf"(^diff --git a/.+ b/{re.escape(fp)}.*?)(?=^diff --git |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        m = chunk_re.search(diff)
        if not m:
            continue
        chunk = m.group(1)
        if used + len(chunk) > max_chars:
            remain = max_chars - used
            if remain > 200:
                parts.append(truncate_section(chunk, remain, fp))
            parts.append(f"\n… [remaining {len(files) - len(parts)} file(s) omitted from diff]")
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts) if parts else truncate_section(diff, max_chars, "diff")


def git_diff(project_root: Path, *, base_ref: str = "", head_ref: str = "", staged: bool = False) -> str:
    root = project_root.resolve()
    if staged:
        cmd = ["git", "diff", "--cached"]
    elif base_ref.strip():
        head = head_ref.strip() or "HEAD"
        cmd = ["git", "diff", base_ref.strip(), head]
    else:
        cmd = ["git", "diff"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(os.environ.get("GIT_DIFF_TIMEOUT_SEC", "60")),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"(git diff failed: {e})"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return f"(git diff failed: {err[:500]})"
    return proc.stdout or ""


def _codegraph_impact_section(project_root: Path, changed_files: list[str], max_chars: int) -> str:
    cg = codegraph_bin()
    if not cg or not changed_files:
        return ""
    cg_dir = project_root / ".codegraph"
    if not cg_dir.is_dir():
        return "(CodeGraph index missing — run `codegraph init -i` in project root)"
    cap = min(max_chars, int(os.environ.get("CODEGRAPH_REVIEW_MAX_CHARS", "4000")))
    lines: list[str] = []
    subset = changed_files[: int(os.environ.get("CODEGRAPH_REVIEW_MAX_FILES", "8"))]
    try:
        proc = subprocess.run(
            [cg, "affected", "-p", str(project_root), *subset],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(os.environ.get("CODEGRAPH_REVIEW_TIMEOUT_SEC", "30")),
        )
        out = (proc.stdout or proc.stderr or "").strip()
        if out:
            lines.append(out)
    except (OSError, subprocess.TimeoutExpired) as e:
        lines.append(f"(codegraph affected failed: {e})")
    for fp in subset[:3]:
        sym = Path(fp).stem
        if not sym:
            continue
        try:
            proc = subprocess.run(
                [cg, "query", sym, "-p", str(project_root), "-l", "5"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            qout = (proc.stdout or "").strip()
            if qout:
                lines.append(f"--- query {sym} ---\n{qout}")
        except (OSError, subprocess.TimeoutExpired):
            break
    body = "\n\n".join(lines)
    return truncate_section(body, cap, "codegraph")


def _mem0_contracts_section(mctx: McpContext, project_id: str, max_chars: int) -> str:
    queries = ("api_contract REST endpoint", "architecture module", "public API contract")
    chunks: list[str] = []
    for q in queries:
        part = mctx.retrieve_chain_body(q, project_id=project_id, top_k_per_scope=4, per_memory_chars=600)
        if part and part != "Ничего не найдено.":
            chunks.append(part)
    body = "\n\n".join(chunks)
    return truncate_section(body, max_chars, "mem0 contracts")


def _architecture_summary_section(mctx: McpContext, project_id: str, max_chars: int) -> str:
    part = mctx.retrieve_chain_body(
        "architecture overview stack modules",
        project_id=project_id,
        top_k_per_scope=3,
        per_memory_chars=800,
    )
    if not part or part == "Ничего не найдено.":
        return "(no architecture facts in Mem0)"
    return truncate_section(part, max_chars, "architecture summary")


def build_review_context(
    mctx: McpContext,
    project_root: Path,
    diff_text: str,
    *,
    project_id: str | None = None,
    max_chars: int | None = None,
) -> str:
    """Assemble review prompt context with priority truncation (diff first)."""
    total = max_chars if max_chars is not None else default_max_chars()
    pid = project_id or mctx.get_project_id()
    root = project_root.resolve()

    diff_budget = int(total * 0.55)
    mem_budget = int(total * 0.22)
    cg_budget = int(total * 0.13)
    arch_budget = total - diff_budget - mem_budget - cg_budget

    diff_body = truncate_diff_by_files(diff_text, diff_budget)
    changed = parse_changed_files(diff_text)
    mem_section = _mem0_contracts_section(mctx, pid, mem_budget)
    cg_section = _codegraph_impact_section(root, changed, cg_budget)
    arch_section = _architecture_summary_section(mctx, pid, arch_budget)

    sections = [
        "=== DIFF ===",
        diff_body or "(empty diff)",
        "\n=== MEM0 CONTRACTS ===",
        mem_section or "(none)",
        "\n=== CODEGRAPH IMPACT ===",
        cg_section or "(none)",
        "\n=== PROJECT SUMMARY ===",
        arch_section,
    ]
    body = "\n".join(sections)
    if len(body) > total:
        body = truncate_section(body, total, "review context")
    return body
