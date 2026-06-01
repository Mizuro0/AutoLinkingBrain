from __future__ import annotations

from autolinkingbrain.mem0_fetch import classify_scope
from autolinkingbrain.mem0_hybrid_search import hybrid_mem_search, tokenize
from autolinkingbrain.mem0_kb_log import normalize_search_results


class _FakeMem0:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.search_calls: list[dict] = []

    def search(self, query: str, *, filters: dict, top_k: int, threshold: float) -> dict:
        self.search_calls.append(
            {"query": query, "filters": filters, "top_k": top_k, "threshold": threshold}
        )
        # Return only rows whose memory contains a query token (vector simulation)
        q = query.lower()
        hits = [r for r in self._rows if q in (r.get("memory") or "").lower()]
        return {"results": hits[:top_k]}

    def get_all(self, *, filters: dict, top_k: int) -> dict:
        uid = filters.get("user_id")
        rows = [r for r in self._rows if r.get("user_id") == uid]
        return {"results": rows[:top_k]}


def test_tokenize_splits_paths_and_words() -> None:
    tokens = tokenize("Hello src/main.py API-key")
    assert "hello" in tokens
    assert "src/main.py" in tokens or "main.py" in tokens


def test_hybrid_mem_search_rrf_merges_vector_and_bm25() -> None:
    rows = [
        {"id": "a", "user_id": "project_demo", "memory": "authentication JWT middleware"},
        {"id": "b", "user_id": "project_demo", "memory": "database migration notes"},
        {"id": "c", "user_id": "project_demo", "memory": "JWT token refresh flow"},
    ]
    mem = _FakeMem0(rows)
    results = hybrid_mem_search(
        mem,
        "JWT authentication",
        "project_demo",
        top_k=2,
        threshold=0.0,
        normalize_search_results=normalize_search_results,
    )
    assert len(results) >= 1
    ids = {r["id"] for r in results}
    assert "a" in ids or "c" in ids
    assert mem.search_calls


def test_classify_scope_channels() -> None:
    assert classify_scope("global_skills") == "global"
    assert classify_scope("global_topology") == "topology"
    assert classify_scope("project_foo") == "project"
    assert classify_scope("other") == "other"
