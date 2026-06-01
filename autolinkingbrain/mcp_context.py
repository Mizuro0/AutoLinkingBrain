"""Shared MCP runtime: project routing, Mem0 read/write helpers, health/recall builders."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from mcp.server.fastmcp.server import Context
from mem0 import Memory

from autolinkingbrain.mcp_constants import (
    GLOBAL_ID,
    INDEXING_MARK_TOKEN,
    INDEXING_STALE_DAYS,
    TOPOLOGY_ID,
)
from autolinkingbrain.mem0_hybrid_search import hybrid_mem_search, hybrid_search_enabled, invalidate_channel_cache
from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0, normalize_search_results
from autolinkingbrain.mem0_privacy import prepare_for_storage, should_block_write
from autolinkingbrain.mem0_provenance import stamp_provenance
from autolinkingbrain.mem0_project_slug import (
    effective_context_path,
    path_from_mcp_root_uri,
    resolve_project_slug,
)


def _suspicious_slugs() -> frozenset[str]:
    raw = os.environ.get("MEM0_SUSPICIOUS_SLUGS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(s.strip().lower() for s in raw.replace(",", ";").split(";") if s.strip())


@dataclass
class McpContext:
    db: Memory
    mcp_roots_paths_cache: list[str] = field(default_factory=list)
    mcp_roots_fetch_done: bool = False
    slug_misleading_warned: bool = False

    async def refresh_project_slug_from_mcp_roots(self, ctx: Context) -> None:
        if self.mcp_roots_fetch_done:
            return
        self.mcp_roots_fetch_done = True
        if os.environ.get("MEM0_USE_MCP_ROOTS", "1").strip().lower() in ("0", "false", "no"):
            return
        try:
            result = await ctx.request_context.session.list_roots()
            roots = getattr(result, "roots", None) or []
            paths: list[str] = []
            for r in roots:
                uri = str(getattr(r, "uri", "") or "")
                p = path_from_mcp_root_uri(uri)
                if p is not None:
                    paths.append(str(p))
            if paths:
                self.mcp_roots_paths_cache = paths
                try:
                    from autolinkingbrain.cursor_agent import sync_project_rules_for_workspace_roots

                    sync_project_rules_for_workspace_roots(paths)
                except Exception:
                    logging.getLogger(__name__).debug(
                        "cursor project rules sync from MCP roots failed",
                        exc_info=True,
                    )
        except Exception:
            logging.getLogger(__name__).debug(
                "MCP roots/list unavailable; Mem0 project slug falls back to cwd / overrides.",
                exc_info=True,
            )

    def get_project_id(
        self,
        project_slug: str | None = None,
        project_root: str | None = None,
        context_path: str | None = None,
    ) -> str:
        slug = resolve_project_slug(
            project_slug=project_slug or "",
            project_root=project_root or "",
            context_path=context_path or "",
            extra_roots=self.mcp_roots_paths_cache,
        )
        if (
            not self.slug_misleading_warned
            and not (project_slug or "").strip()
            and not (context_path or "").strip()
            and slug.lower() in _suspicious_slugs()
        ):
            self.slug_misleading_warned = True
            logging.getLogger(__name__).warning(
                "Mem0 MCP project slug is %r (folder name of cwd). Ensure MEM0_USE_MCP_ROOTS=1 and client "
                "supports roots/list, or set MEM0_PROJECT_SLUG / MCP cwd to ${workspaceFolder}. "
                "Optional: MEM0_SUSPICIOUS_SLUGS to enable this warning.",
                slug,
            )
        return slug

    def project_user_id(
        self,
        project_slug: str | None = None,
        project_root: str | None = None,
        context_path: str | None = None,
    ) -> str:
        return f"project_{self.get_project_id(project_slug, project_root, context_path)}"

    def resolve_project(
        self,
        *,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        infer_from_text: tuple[str, ...] = (),
    ) -> tuple[str, str]:
        ctx = effective_context_path(context_path, *infer_from_text)
        pid = self.get_project_id(project_slug=project_slug, project_root=project_root, context_path=ctx)
        return pid, ctx

    @staticmethod
    def routing_note(project_id: str, context_path: str, used_ctx: str) -> str:
        if used_ctx and not (context_path or "").strip():
            return f" → project_{project_id} (auto-routed from path in payload: {used_ctx})"
        if used_ctx:
            return f" → project_{project_id} (context_path: {used_ctx})"
        return f" → project_{project_id}"

    def mem_search(
        self,
        query: str,
        user_id: str,
        *,
        top_k: int = 20,
        threshold: float = 0.1,
        hybrid: bool | None = None,
    ) -> list[dict]:
        use_hybrid = hybrid_search_enabled() if hybrid is None else hybrid
        if use_hybrid:
            return hybrid_mem_search(
                self.db,
                query,
                user_id,
                top_k=top_k,
                threshold=threshold,
                normalize_search_results=normalize_search_results,
            )
        raw = self.db.search(
            query,
            filters={"user_id": user_id},
            top_k=top_k,
            threshold=threshold,
        )
        return normalize_search_results(raw)

    def mem_add(
        self,
        text: str,
        user_id: str,
        *,
        infer: bool | None = None,
        source: str = "mcp:unknown",
        source_detail: str = "",
    ) -> None:
        stamped = stamp_provenance(text, source, detail=source_detail)
        safe, _modified = prepare_for_storage(stamped)
        if should_block_write(safe):
            logging.getLogger(__name__).warning(
                "Mem0 write blocked by privacy filter (user_id=%s source=%s)", user_id, source
            )
            return
        kwargs: dict = {"user_id": user_id}
        if infer is not None:
            kwargs["infer"] = infer
        self.db.add(safe, **kwargs)
        invalidate_channel_cache(user_id)

    @staticmethod
    def truncate_block(text: str, max_chars: int) -> str:
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        return text[: max_chars - 40] + "\n… [truncated for token budget]\n"

    def build_check_project_health_body(self, project_id: str, project_user_id: str) -> str:
        mark_text = self.latest_indexing_mark_memory(project_user_id)
        health_lines = self.health_status_block(mark_text)
        incoming_rows = self.mem_search(
            f"depends on [{project_id}]",
            TOPOLOGY_ID,
            top_k=int(os.environ.get("MCP_HEALTH_INCOMING_TOP_K", "24")),
            threshold=float(os.environ.get("MCP_HEALTH_INCOMING_THRESHOLD", "0.12")),
            hybrid=True,
        )
        log_mem0(
            "read",
            "mcp.checkProjectHealth.search",
            user_id=TOPOLOGY_ID,
            query=f"depends on [{project_id}]",
            hits=len(incoming_rows),
            hybrid=True,
        )
        max_links = int(os.environ.get("MCP_HEALTH_MAX_INCOMING", "20"))
        slice_rows = incoming_rows[:max_links]
        links = "\n".join([f"• {m.get('memory', '')}" for m in slice_rows]) if slice_rows else "No incoming links."
        if len(incoming_rows) > max_links:
            links += f"\n… and {len(incoming_rows) - max_links} more (raise MCP_HEALTH_MAX_INCOMING or use retrieveChain)."
        return (
            f"=== HEALTH STATUS ===\n{health_lines}\n\n"
            f"=== INCOMING DEPENDENCIES ===\n{links}"
        )

    def retrieve_chain_body(
        self,
        query: str,
        *,
        project_id: str | None = None,
        check_global: bool = True,
        linked_projects: list[str] | None = None,
        top_k_per_scope: int = 6,
        per_memory_chars: int = 900,
        threshold: float | None = None,
    ) -> str:
        current_project = project_id or self.get_project_id()
        search_ids = [f"project_{current_project}"]
        if check_global:
            search_ids.append(GLOBAL_ID)
        if linked_projects:
            search_ids.extend([f"project_{p}" for p in linked_projects])
        thr = (
            float(threshold)
            if threshold is not None
            else float(os.environ.get("MCP_RETRIEVE_THRESHOLD", "0.15"))
        )
        thr = max(0.05, min(thr, 0.5))
        res: list[str] = []
        for u_id in search_ids:
            rows = self.mem_search(query, u_id, top_k=top_k_per_scope, threshold=thr)
            log_mem0(
                "read",
                "mcp.retrieveChain.search",
                user_id=u_id,
                query_preview=(query[:200] + "…") if len(query) > 200 else query,
                hits=len(rows),
                hybrid=hybrid_search_enabled(),
            )
            if not rows:
                continue
            lines: list[str] = []
            for m in rows:
                txt = (m.get("memory") or "").strip()
                if per_memory_chars > 0 and len(txt) > per_memory_chars:
                    txt = txt[: per_memory_chars - 12] + "… [cut]"
                lines.append(txt)
            res.append(f"=== FROM {u_id.upper()} ===\n" + "\n".join(lines))
        return "\n\n".join(res) if res else "Ничего не найдено."

    def latest_indexing_mark_memory(self, project_user_id: str) -> str | None:
        try:
            raw = self.db.get_all(filters={"user_id": project_user_id}, top_k=1000)
            log_mem0(
                "read",
                "mcp.checkProjectHealth.get_all",
                user_id=project_user_id,
                top_k=1000,
                rows=count_get_all_rows(raw),
                purpose="indexing_mark_scan",
            )
        except Exception:
            return None
        rows = raw.get("results", []) if isinstance(raw, dict) else raw or []
        candidates = [
            r
            for r in rows
            if isinstance(r, dict) and self._is_indexing_mark_memory(r.get("memory") or "")
        ]
        if not candidates:
            return None

        def _ts(row: dict) -> str:
            return (row.get("updated_at") or row.get("created_at") or "") or ""

        candidates.sort(key=_ts, reverse=True)
        return candidates[0].get("memory")

    @staticmethod
    def _is_indexing_mark_memory(text: str) -> bool:
        """True only for real markIndexingComplete rows, not autolog bullets mentioning the token."""
        body = (text or "").strip()
        if INDEXING_MARK_TOKEN not in body or "completed_at=" not in body:
            return False
        if body.startswith("[CURSOR]") or "[AUT_LOG" in body[:80]:
            return False
        normalized = body
        if normalized.startswith("[SOURCE:"):
            end = normalized.find("]")
            if end != -1:
                normalized = normalized[end + 1 :].strip()
        return normalized.startswith(INDEXING_MARK_TOKEN)

    @staticmethod
    def health_status_block(mark_text: str | None) -> str:
        if not mark_text:
            return (
                "STATUS: NEEDS_FULL_INDEXING\n"
                "LAST_MARK: (none)\n"
                "REINDEX_PROTOCOL: required"
            )
        age = McpContext.mark_age_days(mark_text)
        if age is None:
            return (
                "STATUS: STALE_INDEXING (cannot_parse_completed_at)\n"
                f"LAST_MARK: {mark_text}\n"
                "REINDEX_PROTOCOL: required"
            )
        if age >= INDEXING_STALE_DAYS:
            return (
                f"STATUS: STALE_INDEXING (age_days={age:.1f}, threshold={INDEXING_STALE_DAYS})\n"
                f"LAST_MARK: {mark_text}\n"
                "REINDEX_PROTOCOL: required"
            )
        return (
            f"STATUS: OK (age_days={age:.1f}, threshold={INDEXING_STALE_DAYS})\n"
            f"LAST_MARK: {mark_text}\n"
            "REINDEX_PROTOCOL: not_required"
        )

    @staticmethod
    def mark_age_days(mark_text: str) -> float | None:
        key = "completed_at="
        pos = mark_text.find(key)
        if pos == -1:
            return None
        rest = mark_text[pos + len(key) :]
        end = rest.find(")")
        if end == -1:
            return None
        ts = rest[:end].strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return None
        if dt.tzinfo:
            now = datetime.now(timezone.utc)
            base = dt.astimezone(timezone.utc)
        else:
            now = datetime.now()
            base = dt
        return (now - base).total_seconds() / 86400.0

    @staticmethod
    def rows_sorted_by_time(raw: object) -> list[dict]:
        rows = raw.get("results", []) if isinstance(raw, dict) else raw or []
        if not isinstance(rows, list):
            return []

        def _ts(row: dict) -> str:
            return (row.get("updated_at") or row.get("created_at") or "") or ""

        out = [r for r in rows if isinstance(r, dict)]
        out.sort(key=_ts, reverse=True)
        return out

    def allowed_delete_user_ids(self) -> frozenset[str]:
        return frozenset({self.project_user_id(), GLOBAL_ID})
