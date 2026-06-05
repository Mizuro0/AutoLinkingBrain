"""Hybrid Mem0 retrieval: vector (Chroma/Mem0) + BM25 keyword, fused with RRF."""

from __future__ import annotations

import math
import os
import re
import time
from collections import Counter

_TOKEN_RE = re.compile(r"[\w.\-/\\]+", re.UNICODE)

# user_id -> (monotonic_ts, rows)
_CHANNEL_CACHE: dict[str, tuple[float, list[dict]]] = {}


def hybrid_search_enabled() -> bool:
    return os.environ.get("MCP_HYBRID_SEARCH", "1").strip().lower() not in ("0", "false", "no")


def _cache_ttl_sec() -> float:
    return max(30.0, float(os.environ.get("MCP_HYBRID_CACHE_SEC", "300")))


def _fetch_cap() -> int:
    return max(50, min(int(os.environ.get("MCP_HYBRID_FETCH_CAP", "1200")), 5000))


def _candidate_pool(top_k: int) -> int:
    mult = max(2, min(int(os.environ.get("MCP_HYBRID_POOL_MULT", "4")), 12))
    return max(top_k, top_k * mult)


def _rrf_k() -> int:
    return max(1, int(os.environ.get("MCP_HYBRID_RRF_K", "60")))


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


def invalidate_channel_cache(user_id: str | None = None) -> None:
    if user_id:
        _CHANNEL_CACHE.pop(user_id, None)
    else:
        _CHANNEL_CACHE.clear()


def _row_id(row: dict, fallback: int) -> str:
    rid = row.get("id")
    if rid is not None and str(rid).strip():
        return str(rid)
    mem = (row.get("memory") or "").strip()
    if mem:
        return mem[:120]
    return f"row:{fallback}"


def _normalize_rows(raw: object) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        rows = list(raw.get("results") or [])
    elif isinstance(raw, list):
        rows = list(raw)
    else:
        return []
    out: list[dict] = []
    for row in rows:
        if isinstance(row, dict) and (row.get("memory") or "").strip():
            out.append(row)
    return out


def _load_channel_rows(mem0, user_id: str) -> list[dict]:
    now = time.monotonic()
    cached = _CHANNEL_CACHE.get(user_id)
    if cached and now - cached[0] < _cache_ttl_sec():
        return cached[1]

    from autolinkingbrain.mem0_fetch import fetch_channel_rows

    rows = fetch_channel_rows(user_id, top_k=_fetch_cap(), db=mem0)
    _CHANNEL_CACHE[user_id] = (now, rows)
    return rows


def _bm25_scores(tokenized_docs: list[list[str]], query_tokens: list[str]) -> list[float]:
    if not tokenized_docs or not query_tokens:
        return [0.0] * len(tokenized_docs)

    n = len(tokenized_docs)
    avgdl = sum(len(d) for d in tokenized_docs) / max(n, 1)
    df: Counter[str] = Counter()
    for tokens in tokenized_docs:
        for term in set(tokens):
            df[term] += 1

    k1 = 1.5
    b = 0.75
    scores: list[float] = []
    for tokens in tokenized_docs:
        tf_map = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for term in query_tokens:
            if term not in df:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            tf = tf_map.get(term, 0)
            denom = tf + k1 * (1 - b + b * dl / avgdl)
            if denom:
                score += idf * (tf * (k1 + 1)) / denom
        scores.append(score)
    return scores


def _bm25_search(rows: list[dict], query: str, top_k: int) -> list[dict]:
    if not rows or not (query or "").strip():
        return []
    docs = [(r.get("memory") or "") for r in rows]
    tokenized = [tokenize(d) for d in docs]
    q_tokens = tokenize(query)
    if not q_tokens:
        return []

    scores = _bm25_scores(tokenized, q_tokens)
    ranked = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)
    out: list[dict] = []
    for idx in ranked:
        if scores[idx] <= 0:
            break
        row = dict(rows[idx])
        row["_bm25_score"] = scores[idx]
        out.append(row)
        if len(out) >= top_k:
            break
    return out


def _rrf_fuse(*ranked_lists: list[dict], top_k: int) -> list[dict]:
    k = _rrf_k()
    scores: dict[str, float] = {}
    rows_by_id: dict[str, dict] = {}

    for lst in ranked_lists:
        for rank, row in enumerate(lst, start=1):
            rid = _row_id(row, rank)
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
            if rid not in rows_by_id:
                rows_by_id[rid] = row

    ordered = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    fused: list[dict] = []
    for rid in ordered[:top_k]:
        row = dict(rows_by_id[rid])
        row["_rrf_score"] = scores[rid]
        fused.append(row)
    return fused


def hybrid_mem_search(
    mem0,
    query: str,
    user_id: str,
    *,
    top_k: int = 20,
    threshold: float = 0.1,
    normalize_search_results,
) -> list[dict]:
    """
    Vector + BM25 over channel corpus, merged with reciprocal rank fusion (RRF).
    Falls back to vector-only if query/channel empty or BM25 finds nothing.
    """
    q = (query or "").strip()
    if not q:
        return []

    pool = _candidate_pool(top_k)
    channel_rows = _load_channel_rows(mem0, user_id)
    bm25_rows = _bm25_search(channel_rows, q, pool)

    from autolinkingbrain.mem0_fetch import _fetch_use_sqlite

    if _fetch_use_sqlite():
        return bm25_rows[:top_k]

    thr = max(0.0, min(float(threshold), 0.5))
    try:
        raw_vec = mem0.search(q, filters={"user_id": user_id}, top_k=pool, threshold=thr)
        vector_rows = normalize_search_results(raw_vec)
    except Exception:
        vector_rows = []

    if vector_rows and bm25_rows:
        return _rrf_fuse(vector_rows, bm25_rows, top_k=top_k)
    if vector_rows:
        return vector_rows[:top_k]
    if bm25_rows:
        return bm25_rows[:top_k]
    return []
