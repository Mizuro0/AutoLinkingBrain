from __future__ import annotations

import logging
import os
import pathlib
import sys
import warnings
from datetime import datetime, timezone


# При cwd="${workspaceFolder}" каталог репозитория может не быть в sys.path.
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Полный лог stderr + logging в файл (stdout не трогаем — JSON-RPC). См. mcp_full_log.py, MCP_FULL_LOG=0 чтобы выкл.
from autolinkingbrain.mcp_full_log import install_mcp_full_capture

install_mcp_full_capture(_REPO_ROOT)
warnings.filterwarnings("ignore")

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.server import Context
    from mem0 import Memory

    from autolinkingbrain.mem0_hybrid_search import hybrid_mem_search, hybrid_search_enabled, invalidate_channel_cache
    from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0, normalize_search_results
    from autolinkingbrain.mem0_lifecycle import is_stale_memory, stale_days_default
    from autolinkingbrain.mem0_privacy import prepare_for_storage, should_block_write
    from autolinkingbrain.mem0_provenance import stamp_provenance
    from autolinkingbrain.mem0_project_slug import effective_context_path, path_from_mcp_root_uri, resolve_project_slug
    from autolinkingbrain.mem0_settings import mem0_vector_config
except ImportError as e:
    with open(os.path.join(_REPO_ROOT, "critical_error.log"), "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] ImportError: {e}\n")
    raise SystemExit(1) from e

config = mem0_vector_config()
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    mem0_db = Memory.from_config(config_dict=config)
_MCP_INSTRUCTIONS = """AutoLinkingBrain — semantic memory and cross-repo dependency contracts (Mem0/Chroma).

Pair with CodeGraph when both MCP servers are configured:
- CodeGraph FIRST for CODE STRUCTURE: symbols, callers/callees, trace paths, impact radius, file index (.codegraph/ must exist — run `codegraph init -i` per repo).
- AutoLinkingBrain for MEMORY & CONTRACTS: prior decisions, architecture notes, bugfixes, cross-repo dependencies.

Tool routing:
1. Repo overview / onboarding: checkProjectHealth (or sessionContextPack) BEFORE grep/read for indexing state and incoming dependencies.
2. "What we decided / documented": retrieveChain or sessionContextPack — not grep (hybrid BM25+vector by default).
3. "Where in code / who calls X / impact of change": CodeGraph (codegraph_search, codegraph_trace, codegraph_explore, codegraph_impact) — not blind file scans.
4. Cross-repo public API changes: retrieveChain with linked_projects BEFORE editing; registerDependency when indexing outbound links.
5. After full project scan: markIndexingComplete (FINAL_INDEXING_MARK); use storeKnowledge for facts (English body, tech/scenario metadata).

Writes via storeKnowledge, registerDependency, markIndexingComplete: English only, one fact per entry when possible.

Monorepo / multi-repo folder (e.g. feature/backend + feature/crm opened together): pass context_path with the
file or subproject path so memories go to project_backend / project_crm — not project_feature.
If context_path is omitted, the server auto-infers a path from text/reason/summary/query fields when present.
"""

mcp = FastMCP("AutoLinkingBrain", instructions=_MCP_INSTRUCTIONS)

GLOBAL_ID = "global_skills"
TOPOLOGY_ID = "global_topology"  # Специальный канал для хранения связей
_ALLOWED_LINK_TYPES = frozenset({"module", "api"})

# Протокол индексации: в канале project_<cwd> в тексте памяти должна встречаться эта подстрока.
# check_project_health ищет её перебором записей (get_all), а не семантическим search.
INDEXING_MARK_TOKEN = "FINAL_INDEXING_MARK"
INDEXING_STALE_DAYS = 7

# Warn when MCP slug looks like a generic OS profile folder (optional; MEM0_SUSPICIOUS_SLUGS).
_slug_misleading_warned = False


def _suspicious_slugs() -> frozenset[str]:
    raw = os.environ.get("MEM0_SUSPICIOUS_SLUGS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(s.strip().lower() for s in raw.replace(",", ";").split(";") if s.strip())

# Все MCP roots (не только первый) — для monorepo-папок вроде feature/{backend,crm,...}.
_mcp_roots_paths_cache: list[str] = []
_mcp_roots_fetch_done = False


async def refresh_project_slug_from_mcp_roots(ctx: Context) -> None:
    """
    Один раз за жизнь процесса MCP запрашивает roots у клиента (Cursor) и кэширует все file:// пути.

    Так resolve_project_slug видит workspace root даже если os.getcwd() у процесса MCP «левый».
    """
    global _mcp_roots_paths_cache, _mcp_roots_fetch_done
    if _mcp_roots_fetch_done:
        return
    _mcp_roots_fetch_done = True
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
            _mcp_roots_paths_cache = paths
    except Exception:
        logging.getLogger(__name__).debug(
            "MCP roots/list unavailable; Mem0 project slug falls back to cwd / overrides.",
            exc_info=True,
        )


def get_project_id(
    project_slug: str | None = None,
    project_root: str | None = None,
    context_path: str | None = None,
) -> str:
    """
    Канал Mem0 project_<slug>.

    При monorepo-папке (feature/backend, feature/crm) context_path к редактируемому файлу
    направляет запись в project_backend / project_crm, а не в project_feature.
    """
    global _slug_misleading_warned
    slug = resolve_project_slug(
        project_slug=project_slug or "",
        project_root=project_root or "",
        context_path=context_path or "",
        extra_roots=_mcp_roots_paths_cache,
    )
    if (
        not _slug_misleading_warned
        and not (project_slug or "").strip()
        and not (context_path or "").strip()
        and slug.lower() in _suspicious_slugs()
    ):
        _slug_misleading_warned = True
        logging.getLogger(__name__).warning(
            "Mem0 MCP project slug is %r (folder name of cwd). Ensure MEM0_USE_MCP_ROOTS=1 and client "
            "supports roots/list, or set MEM0_PROJECT_SLUG / MCP cwd to ${workspaceFolder}. "
            "Optional: MEM0_SUSPICIOUS_SLUGS to enable this warning.",
            slug,
        )
    return slug


def _project_user_id(
    project_slug: str | None = None,
    project_root: str | None = None,
    context_path: str | None = None,
) -> str:
    return f"project_{get_project_id(project_slug=project_slug, project_root=project_root, context_path=context_path)}"


def _resolve_project(
    *,
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    infer_from_text: tuple[str, ...] = (),
) -> tuple[str, str]:
    """Return (project_id, effective_context_path). Infers path from text when context_path omitted."""
    ctx = effective_context_path(context_path, *infer_from_text)
    pid = get_project_id(project_slug=project_slug, project_root=project_root, context_path=ctx)
    return pid, ctx


def _routing_note(project_id: str, context_path: str, used_ctx: str) -> str:
    if used_ctx and not (context_path or "").strip():
        return f" → project_{project_id} (auto-routed from path in payload: {used_ctx})"
    if used_ctx:
        return f" → project_{project_id} (context_path: {used_ctx})"
    return f" → project_{project_id}"


def _mem_search(
    query: str,
    user_id: str,
    *,
    top_k: int = 20,
    threshold: float = 0.1,
    hybrid: bool | None = None,
) -> list[dict]:
    """Mem0 search; retrieveChain uses hybrid BM25+vector when MCP_HYBRID_SEARCH=1."""
    use_hybrid = hybrid_search_enabled() if hybrid is None else hybrid
    if use_hybrid:
        rows = hybrid_mem_search(
            mem0_db,
            query,
            user_id,
            top_k=top_k,
            threshold=threshold,
            normalize_search_results=normalize_search_results,
        )
        return rows

    raw = mem0_db.search(
        query,
        filters={"user_id": user_id},
        top_k=top_k,
        threshold=threshold,
    )
    return normalize_search_results(raw)


def _mem_add(
    text: str,
    user_id: str,
    *,
    infer: bool | None = None,
    source: str = "mcp:unknown",
    source_detail: str = "",
) -> None:
    """Write to Mem0 (provenance + privacy) and drop hybrid BM25 cache."""
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
    mem0_db.add(safe, **kwargs)
    invalidate_channel_cache(user_id)


def _truncate_block(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 40] + "\n… [truncated for token budget]\n"


def _build_check_project_health_body(project_id: str, project_user_id: str) -> str:
    """Текст health + incoming (без внешней обрезки по токенам)."""
    mark_text = _latest_indexing_mark_memory(project_user_id)
    health_lines = _health_status_block(mark_text)
    incoming_rows = _mem_search(
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


def _retrieve_chain_body(
    query: str,
    *,
    project_id: str | None = None,
    check_global: bool = True,
    linked_projects: list[str] | None = None,
    top_k_per_scope: int = 6,
    per_memory_chars: int = 900,
    threshold: float | None = None,
) -> str:
    current_project = project_id or get_project_id()
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
        rows = _mem_search(query, u_id, top_k=top_k_per_scope, threshold=thr)
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


def _latest_indexing_mark_memory(project_user_id: str) -> str | None:
    """Последняя по времени запись канала проекта, содержащая INDEXING_MARK_TOKEN."""
    try:
        raw = mem0_db.get_all(filters={"user_id": project_user_id}, top_k=1000)
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
        r for r in rows if isinstance(r, dict) and INDEXING_MARK_TOKEN in (r.get("memory") or "")
    ]
    if not candidates:
        return None

    def _ts(row: dict) -> str:
        return (row.get("updated_at") or row.get("created_at") or "") or ""

    candidates.sort(key=_ts, reverse=True)
    return candidates[0].get("memory")


def _completed_at_from_mark(mark_text: str) -> datetime | None:
    """Парсит completed_at из строки mark_indexing_complete (… (completed_at=ISO) …)."""
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
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _mark_age_days(mark_text: str) -> float | None:
    dt = _completed_at_from_mark(mark_text)
    if dt is None:
        return None
    if dt.tzinfo:
        now = datetime.now(timezone.utc)
        base = dt.astimezone(timezone.utc)
    else:
        now = datetime.now()
        base = dt
    return (now - base).total_seconds() / 86400.0


def _health_status_block(mark_text: str | None) -> str:
    """Строки STATUS / REINDEX_PROTOCOL для согласования с User rules."""
    if not mark_text:
        return (
            "STATUS: NEEDS_FULL_INDEXING\n"
            "LAST_MARK: (none)\n"
            "REINDEX_PROTOCOL: required"
        )
    age = _mark_age_days(mark_text)
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


def _link_line(source_project: str, target_project: str, link_type: str, reason: str) -> str:
    """Строгий формат строки связи — по нему ищутся входящие зависимости в check_project_health."""
    return (
        f"[LINK] [{source_project}] depends on [{target_project}] via [{link_type.upper()}]. "
        f"Contract: {reason}"
    )


@mcp.tool(name="registerDependency")
async def register_dependency(
    target_project: str,
    link_type: str,
    reason: str,
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    *,
    ctx: Context,
) -> str:
    """
    Регистрирует связь между проектами.

    target_project: Имя проекта или сервиса, от которого мы зависим.
    link_type: Тип связи: 'module' (через Gradle) или 'api' (REST, gRPC, GraphQL).
    reason: Краткое описание контракта (какие данные гоняем или какие методы вызываем).
    context_path: Путь к файлу/директории, над которым работает агент (для monorepo-папок).

    Строка в базе всегда в виде: [LINK] [текущий_проект] depends on [target_project] via [...].
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    target = (target_project or "").strip()
    if not target:
        return "Ошибка: target_project не может быть пустым."

    lt = (link_type or "").strip().lower()
    if lt not in _ALLOWED_LINK_TYPES:
        return (
            "Ошибка: link_type должен быть 'module' или 'api' "
            f"(регистр не важен). Получено: {link_type!r}."
        )

    reason_clean = (reason or "").strip()
    if not reason_clean:
        return "Ошибка: reason не может быть пустым."

    rmax = int(os.environ.get("MCP_LINK_REASON_MAX_CHARS", "420"))
    if rmax > 0 and len(reason_clean) > rmax:
        reason_clean = reason_clean[: rmax - 25] + "… [reason truncated]"

    source_project, used_ctx = _resolve_project(
        project_slug=project_slug,
        project_root=project_root,
        context_path=context_path,
        infer_from_text=(reason,),
    )
    text = _link_line(source_project, target, lt, reason_clean)

    _mem_add(text, TOPOLOGY_ID, source="mcp:registerDependency", source_detail=f"target={target}")
    log_mem0(
        "write",
        "mcp.registerDependency",
        user_id=TOPOLOGY_ID,
        target_project=target,
        link_type=lt,
        source_project=source_project,
    )
    return f"Связь {source_project} -> {target} ({lt}) зарегистрирована.{_routing_note(source_project, context_path, used_ctx)}"


@mcp.tool(name="markIndexingComplete")
async def mark_indexing_complete(
    summary: str = "",
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    *,
    ctx: Context,
) -> str:
    """
    Фиксирует завершение полной индексации текущего проекта (протокол FINAL_INDEXING_MARK).

    В канал project_<slug> добавляется строка, обязательно содержащая подстроку FINAL_INDEXING_MARK
    в начале содержимого памяти — именно её находит check_project_health (через get_all, не search).

    Не вставляйте маркер только внутрь store_knowledge с tech/scenario — для отчёта о индексации
    вызывайте этот инструмент.
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    now = datetime.now().isoformat()
    line = f"{INDEXING_MARK_TOKEN} (completed_at={now})"
    smax = int(os.environ.get("MCP_INDEXING_SUMMARY_MAX_CHARS", "900"))
    sm = (summary or "").strip()
    if sm:
        if smax > 0 and len(sm) > smax:
            sm = sm[: smax - 20] + "… [truncated]"
        line += f": {sm}"
    project_id, used_ctx = _resolve_project(
        project_slug=project_slug,
        project_root=project_root,
        context_path=context_path,
        infer_from_text=(summary,),
    )
    p_user_id = f"project_{project_id}"
    _mem_add(line, p_user_id, source="mcp:markIndexingComplete", source_detail=f"project={project_id}")
    log_mem0("write", "mcp.markIndexingComplete", user_id=p_user_id, project_id=project_id)
    return f"Отметка индексации сохранена в канале проекта.{_routing_note(project_id, context_path, used_ctx)}"


@mcp.tool(name="checkProjectHealth")
async def check_project_health(
    max_response_chars: int = 12000,
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    *,
    ctx: Context,
) -> str:
    """
    Проверяет отметку индексации и входящие связи (кто зависит от нас).

    Индексация: подстрока FINAL_INDEXING_MARK в канале project_<slug> (последняя запись по времени).
    Ответ содержит STATUS: и REINDEX_PROTOCOL: (required | not_required) — ориентир для User rules.

    Отметку ставит mark_indexing_complete (не store_knowledge).

    max_response_chars: верхний предел размера ответа (экономия токенов). Переменная окружения
    MCP_HEALTH_MAX_RESPONSE_CHARS переопределяет значение по умолчанию из параметра.
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    project_id, used_ctx = _resolve_project(
        project_slug=project_slug,
        project_root=project_root,
        context_path=context_path,
    )
    body = _build_check_project_health_body(project_id, f"project_{project_id}")
    cap = int(os.environ.get("MCP_HEALTH_MAX_RESPONSE_CHARS", str(max_response_chars)))
    return _truncate_block(body, max(4000, cap))


@mcp.tool(name="storeKnowledge")
async def store_knowledge(
    text: str,
    tech: str,
    scenario: str,
    scope: str = "project",
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
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
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    project_id, used_ctx = _resolve_project(
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
    enriched_text = f"[{tech.upper()}] [{scenario.upper()}] (Updated: {now}): {body}"

    u_ids: list[str] = []
    if scope in ("project", "both"):
        u_ids.append(f"project_{project_id}")
    if scope in ("global", "both"):
        u_ids.append(GLOBAL_ID)

    for u_id in u_ids:
        _mem_add(
            enriched_text,
            u_id,
            source="mcp:storeKnowledge",
            source_detail=f"tech={tech} scenario={scenario} scope={scope}",
        )
    log_mem0("write", "mcp.storeKnowledge", scope=scope, user_ids=u_ids, tech=tech, scenario=scenario, project_id=project_id)
    return f"Сохранено в {scope}.{_routing_note(project_id, context_path, used_ctx)}"


@mcp.tool(name="retrieveChain")
async def retrieve_chain(
    query: str,
    check_global: bool = True,
    linked_projects: list[str] | None = None,
    top_k_per_scope: int = 6,
    max_response_chars: int = 12000,
    per_memory_chars: int = 900,
    similarity_threshold: float = 0.15,
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
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    project_id, _used_ctx = _resolve_project(
        project_slug=project_slug,
        project_root=project_root,
        context_path=context_path,
        infer_from_text=(query,),
    )
    text = _retrieve_chain_body(
        query,
        project_id=project_id,
        check_global=check_global,
        linked_projects=linked_projects,
        top_k_per_scope=top_k_per_scope,
        per_memory_chars=per_memory_chars,
        threshold=similarity_threshold,
    )
    cap = int(os.environ.get("MCP_RETRIEVE_MAX_RESPONSE_CHARS", str(max_response_chars)))
    return _truncate_block(text, max(4000, cap))


@mcp.tool(name="sessionContextPack")
async def session_context_pack(
    recall_query: str = "architecture dependencies API stack decisions",
    top_k_per_scope: int = 4,
    max_total_chars: int = 14000,
    check_global: bool = True,
    linked_projects: list[str] | None = None,
    per_memory_chars: int = 850,
    similarity_threshold: float = 0.15,
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    *,
    ctx: Context,
) -> str:
    """
    Один вызов вместо двух: то же, что check_project_health, плюс компактный retrieve_chain по recall_query.

    Меньше round-trip инструментов → меньше накладных расходов; общий потолок max_total_chars.
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    project_id, _used_ctx = _resolve_project(
        project_slug=project_slug,
        project_root=project_root,
        context_path=context_path,
        infer_from_text=(recall_query,),
    )
    parts = [
        _build_check_project_health_body(project_id, f"project_{project_id}"),
        "\n=== SESSION RECALL ===\n",
        _retrieve_chain_body(
            recall_query,
            project_id=project_id,
            check_global=check_global,
            linked_projects=linked_projects,
            top_k_per_scope=top_k_per_scope,
            per_memory_chars=per_memory_chars,
            threshold=similarity_threshold,
        ),
    ]
    body = "".join(parts)
    log_mem0(
        "read",
        "mcp.sessionContextPack",
        project=project_id,
        recall_preview=(recall_query[:120] + "…") if len(recall_query) > 120 else recall_query,
        max_total_chars=max_total_chars,
    )
    cap = int(os.environ.get("MCP_SESSION_PACK_MAX_CHARS", str(max_total_chars)))
    return _truncate_block(body, max(6000, cap))


def _allowed_delete_user_ids() -> frozenset[str]:
    """Удалять можно только из канала текущего проекта или global_skills (не топология)."""
    return frozenset({_project_user_id(), GLOBAL_ID})


@mcp.tool(name="listRecentMemories")
async def list_recent_memories(
    limit: int = 35,
    include_global: bool = False,
    fetch_cap: int = 160,
    preview_chars: int = 90,
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    *,
    ctx: Context,
) -> str:
    """
    Список последних записей Mem0 для ревью жизненного цикла: id, даты, короткий превью-текст.

    Сортировка по updated_at (новые сверху). Не удаляет ничего.
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    limit = max(1, min(limit, 100))
    fetch_cap = max(limit, min(fetch_cap, 400))
    preview_chars = max(40, min(preview_chars, 220))
    project_id, used_ctx = _resolve_project(
        project_slug=project_slug,
        project_root=project_root,
        context_path=context_path,
    )
    p_user_id = f"project_{project_id}"
    lines: list[str] = []

    def _append_channel(label: str, uid: str) -> None:
        raw = mem0_db.get_all(filters={"user_id": uid}, top_k=fetch_cap)
        log_mem0("read", "mcp.listRecentMemories.get_all", user_id=uid, top_k=fetch_cap, rows=count_get_all_rows(raw))
        rows = _rows_sorted_by_time(raw)
        lines.append(f"## {label} (`{uid}`) — showing up to {limit}")
        for row in rows[:limit]:
            mid = str(row.get("id", ""))
            preview = (row.get("memory") or "").replace("\n", " ").strip()[:preview_chars]
            if len((row.get("memory") or "")) > preview_chars:
                preview += "…"
            ts = row.get("updated_at") or row.get("created_at") or ""
            lines.append(f"• id={mid} | {ts} | {preview}")
        lines.append("")

    _append_channel("Project", p_user_id)
    if include_global:
        _append_channel("Global", GLOBAL_ID)

    body = "\n".join(lines).strip()
    return _truncate_block(
        f"(project slug: {project_id})\n\n{body}",
        int(os.environ.get("MCP_LIST_MEMORIES_MAX_CHARS", "18000")),
    )


def _rows_sorted_by_time(raw: object) -> list[dict]:
    rows = raw.get("results", []) if isinstance(raw, dict) else raw or []
    if not isinstance(rows, list):
        return []

    def _ts(row: dict) -> str:
        return (row.get("updated_at") or row.get("created_at") or "") or ""

    rows = [r for r in rows if isinstance(r, dict)]
    rows.sort(key=_ts, reverse=True)
    return rows


@mcp.tool(name="listStaleMemories")
async def list_stale_memories(
    stale_days: int = 0,
    limit: int = 40,
    include_global: bool = False,
    fetch_cap: int = 200,
    preview_chars: int = 90,
    project_slug: str = "",
    project_root: str = "",
    context_path: str = "",
    *,
    ctx: Context,
) -> str:
    """
    Записи Mem0 старше порога (MEM0_STALE_DAYS, по умолчанию 90 дней) — для ревью и очистки.

    Сортировка: самые старые сверху. Ничего не удаляет.
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    threshold = stale_days if stale_days > 0 else stale_days_default()
    limit = max(1, min(limit, 100))
    fetch_cap = max(limit, min(fetch_cap, 400))
    preview_chars = max(40, min(preview_chars, 220))
    project_id, _used_ctx = _resolve_project(
        project_slug=project_slug,
        project_root=project_root,
        context_path=context_path,
    )
    p_user_id = f"project_{project_id}"
    lines: list[str] = [f"(stale threshold: {threshold} days, project slug: {project_id})\n"]

    def _append_channel(label: str, uid: str) -> None:
        raw = mem0_db.get_all(filters={"user_id": uid}, top_k=fetch_cap)
        log_mem0("read", "mcp.listStaleMemories.get_all", user_id=uid, top_k=fetch_cap, rows=count_get_all_rows(raw))
        rows = _rows_sorted_by_time(raw)
        stale_rows = [r for r in rows if is_stale_memory(r, stale_days=threshold)]
        stale_rows.sort(
            key=lambda r: (r.get("updated_at") or r.get("created_at") or ""),
        )
        lines.append(f"## {label} (`{uid}`) — {len(stale_rows)} stale, showing up to {limit}")
        for row in stale_rows[:limit]:
            mid = str(row.get("id", ""))
            preview = (row.get("memory") or "").replace("\n", " ").strip()[:preview_chars]
            if len((row.get("memory") or "")) > preview_chars:
                preview += "…"
            ts = row.get("updated_at") or row.get("created_at") or ""
            lines.append(f"• id={mid} | {ts} | {preview}")
        lines.append("")

    _append_channel("Project", p_user_id)
    if include_global:
        _append_channel("Global", GLOBAL_ID)

    body = "\n".join(lines).strip()
    return _truncate_block(
        body,
        int(os.environ.get("MCP_LIST_MEMORIES_MAX_CHARS", "18000")),
    )


@mcp.tool(name="deleteMemory")
async def delete_memory(memory_id: str, *, ctx: Context) -> str:
    """
    Удаляет одну запись по id (из viewer или из listRecentMemories).

    Разрешено только для канала project_<slug> и global_skills — не для global_topology.
    """
    await refresh_project_slug_from_mcp_roots(ctx)
    mid = (memory_id or "").strip()
    if not mid:
        return "Ошибка: memory_id пустой."

    row = mem0_db.get(mid)
    if not row:
        return f"Не найдено: {mid!r}."

    uid = row.get("user_id")
    if uid not in _allowed_delete_user_ids():
        return (
            f"Отказ: запись в канале {uid!r} — удаление через этот инструмент запрещено "
            "(разрешены только текущий project_* и global_skills)."
        )

    mem0_db.delete(mid)
    log_mem0("write", "mcp.deleteMemory", memory_id=mid, user_id=uid)
    return f"Удалено: {mid} (канал {uid})."


if __name__ == "__main__":
    mcp.run()
