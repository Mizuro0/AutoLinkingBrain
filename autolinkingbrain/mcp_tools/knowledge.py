"""Knowledge storage and retrieval tools."""

from __future__ import annotations

import os
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from autolinkingbrain.mcp_constants import GLOBAL_ID
from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.mem0_kb_log import log_mem0
from autolinkingbrain.mem0_settings import mcp_store_infer_enabled


def register(mcp: FastMCP, mctx: McpContext) -> None:
    @mcp.tool(name="storeKnowledge")
    async def store_knowledge(
        text: str,
        tech: str,
        scenario: str,
        scope: str = "project",
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        code_role: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Сохранение фактов (технологии, архитектура, багфиксы).

        Каналы Mem0 (user_id): при scope='project' — только текущий проект; 'global' — только global_skills;
        'both' — запись и в project_<slug>, и в global_skills (общий опыт + локальный контекст).
        context_path: путь к файлу/директории — для monorepo-папок определяет project_<slug> по подпроекту.
        Если не передан — сервер попытается извлечь путь из поля text.

        Завершение индексации по протоколу — отдельным вызовом mark_indexing_complete(), не через этот текст.

        Запись напрямую в Chroma (infer=False по умолчанию) — без LLM-extraction через Ollama.
        MEM0_MCP_INFER=1 — включить медленный infer (не рекомендуется при массовой индексации).
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        project_id, used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
            infer_from_text=(text,),
        )
        now = datetime.now().isoformat()
        body = (text or "").strip()
        tmax = int(os.environ.get("MCP_STORE_KNOWLEDGE_BODY_MAX_CHARS", "5500"))
        if tmax > 0 and len(body) > tmax:
            body = body[: tmax - 28] + "\n… [body truncated for storage/token budget]"
        role_tag = f" [ROLE:{code_role.strip().upper()}]" if (code_role or "").strip() else ""
        enriched_text = f"[{tech.upper()}] [{scenario.upper()}]{role_tag} (Updated: {now}): {body}"

        u_ids: list[str] = []
        if scope in ("project", "both"):
            u_ids.append(f"project_{project_id}")
        if scope in ("global", "both"):
            u_ids.append(GLOBAL_ID)

        for u_id in u_ids:
            mctx.mem_add(
                enriched_text,
                u_id,
                infer=mcp_store_infer_enabled(),
                source="mcp:storeKnowledge",
                source_detail=f"tech={tech} scenario={scenario} scope={scope} code_role={code_role or '-'}",
            )
        log_mem0(
            "write",
            "mcp.storeKnowledge",
            scope=scope,
            user_ids=u_ids,
            stored_chars=len(enriched_text),  # cloud-agent output tokens spent to write the fact
            tech=tech,
            scenario=scenario,
            project_id=project_id,
        )
        return f"Сохранено в {scope}.{mctx.routing_note(project_id, context_path, used_ctx)}"

    @mcp.tool(name="retrieveChain")
    async def retrieve_chain(
        query: str,
        check_global: bool = True,
        linked_projects: list[str] | None = None,
        top_k_per_scope: int = 6,
        max_response_chars: int = 12000,
        per_memory_chars: int = 900,
        similarity_threshold: float = 0.15,
        facts_only: bool = True,
        project_slug: str = "",
        project_root: str = "",
        context_path: str = "",
        *,
        ctx: Context,
    ) -> str:
        """
        Семантический поиск по текущему проекту, global_skills и (опционально) linked-проектам.

        top_k_per_scope: сколько воспоминаний максимум с каждого канала (по умолчанию 6).
        max_response_chars / per_memory_chars: ограничение длины ответа и одной записи.
        similarity_threshold: порог Mem0 vector search (BM25 в hybrid не использует порог).
        Hybrid BM25+vector (RRF) включён по умолчанию (MCP_HYBRID_SEARCH=1) — точнее для keyword + semantic.
        facts_only: по умолчанию true — исключает autolog [CURSOR]/[AUT_LOG]; только storeKnowledge-факты.
        """
        await mctx.refresh_project_slug_from_mcp_roots(ctx)
        project_id, _used_ctx = mctx.resolve_project(
            project_slug=project_slug,
            project_root=project_root,
            context_path=context_path,
            infer_from_text=(query,),
        )
        text = mctx.retrieve_chain_body(
            query,
            project_id=project_id,
            check_global=check_global,
            linked_projects=linked_projects,
            top_k_per_scope=top_k_per_scope,
            per_memory_chars=per_memory_chars,
            threshold=similarity_threshold,
            facts_only=facts_only,
        )
        cap = int(os.environ.get("MCP_RETRIEVE_MAX_RESPONSE_CHARS", str(max_response_chars)))
        return mctx.truncate_block(text, max(4000, cap))
