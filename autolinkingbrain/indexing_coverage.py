"""Indexing coverage metrics for checkProjectHealth and markIndexingComplete gate."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from autolinkingbrain.mcp_constants import INDEXING_MARK_TOKEN, TOPOLOGY_ID

_SCENARIO_RE = re.compile(r"\[([A-Z][A-Z0-9_]*)\]")
_ROLE_RE = re.compile(r"\[ROLE:([A-Z][A-Z0-9_]*)\]", re.I)
_OUTBOUND_LINK_RE = re.compile(
    r"\[LINK\]\s*\[([^\]]+)\]\s+depends on\s+\[([^\]]+)\]",
    re.IGNORECASE,
)

_AUTOLOG_MARKERS = ("[CURSOR]", "[AUT_LOG", "AUT_LOG_LLAMA")


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def indexing_min_facts() -> int:
    return max(0, _env_int("MEM0_INDEXING_MIN_FACTS", 8))


def indexing_min_outbound_deps() -> int:
    return max(0, _env_int("MEM0_INDEXING_MIN_OUTBOUND_DEPS", 0))


def indexing_required_scenarios() -> frozenset[str]:
    raw = os.environ.get("MEM0_INDEXING_REQUIRED_SCENARIOS", "architecture,api_contract").strip()
    if not raw:
        return frozenset()
    parts = [p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()]
    return frozenset(parts)


def indexing_strict() -> bool:
    return os.environ.get("MEM0_INDEXING_STRICT", "1").strip().lower() in ("1", "true", "yes")


def is_countable_fact(memory_text: str) -> bool:
    """True if memory row counts toward indexing fact coverage."""
    body = (memory_text or "").strip()
    if not body or INDEXING_MARK_TOKEN in body:
        return False
    head = body[:120]
    if any(m in head for m in _AUTOLOG_MARKERS):
        return False
    if body.startswith("[LINK]"):
        return False
    if body.startswith("[SOURCE:") and INDEXING_MARK_TOKEN in body:
        return False
    return True


def parse_scenario_tags(memory_text: str) -> set[str]:
    """Extract scenario-like tags from storeKnowledge enriched text."""
    body = (memory_text or "").strip()
    if body.startswith("[SOURCE:"):
        end = body.find("]")
        if end != -1:
            body = body[end + 1 :].strip()
    tags = _SCENARIO_RE.findall(body[:280])
    out: set[str] = set()
    for i, tag in enumerate(tags):
        low = tag.lower()
        if i == 0 and low in ("kotlin", "java", "python", "node", "spring", "ktor", "gradle", "mem0", "mcp"):
            continue
        if low in ("updated", "source"):
            continue
        out.add(low)
    return out


def parse_code_role_tags(memory_text: str) -> set[str]:
    return {m.group(1).upper() for m in _ROLE_RE.finditer(memory_text or "")}


def count_outbound_links(topology_memories: list[str], project_slug: str) -> int:
    slug = (project_slug or "").strip().lower()
    if not slug:
        return 0
    count = 0
    for text in topology_memories:
        m = _OUTBOUND_LINK_RE.search(text or "")
        if not m:
            continue
        source = (m.group(1) or "").strip().lower()
        if source == slug:
            count += 1
    return count


@dataclass
class IndexingCoverage:
    fact_count: int = 0
    scenarios_found: set[str] = field(default_factory=set)
    outbound_deps: int = 0
    code_roles_found: set[str] = field(default_factory=set)
    min_facts: int = 0
    required_scenarios: frozenset[str] = field(default_factory=frozenset)
    min_outbound_deps: int = 0
    gaps: list[str] = field(default_factory=list)

    @property
    def sufficient(self) -> bool:
        return not self.gaps

    @property
    def has_architecture_summary(self) -> bool:
        return "architecture" in self.scenarios_found

    def compute_gaps(self) -> list[str]:
        gaps: list[str] = []
        if self.fact_count < self.min_facts:
            gaps.append(f"facts below minimum ({self.fact_count} < {self.min_facts})")
        missing = sorted(self.required_scenarios - self.scenarios_found)
        for sc in missing:
            gaps.append(f"missing scenario '{sc}'")
        if self.outbound_deps < self.min_outbound_deps:
            gaps.append(
                f"outbound deps below minimum ({self.outbound_deps} < {self.min_outbound_deps})"
            )
        self.gaps = gaps
        return gaps

    def format_block(self) -> str:
        self.compute_gaps()
        scenarios = ", ".join(sorted(self.scenarios_found)) or "(none)"
        required = ", ".join(sorted(self.required_scenarios)) or "(none)"
        gaps_line = "; ".join(self.gaps) if self.gaps else "(none)"
        status = "sufficient" if self.sufficient else "insufficient"
        roles = ", ".join(sorted(self.code_roles_found)) or "(none)"
        return (
            f"FACTS: {self.fact_count} (min {self.min_facts})\n"
            f"SCENARIOS: {scenarios} (required: {required})\n"
            f"CODE ROLES: {roles}\n"
            f"OUTBOUND DEPS: {self.outbound_deps} (min {self.min_outbound_deps})\n"
            f"GAPS: {gaps_line}\n"
            f"COVERAGE_STATUS: {status}"
        )


def analyze_indexing_coverage(
    project_memories: list[str],
    topology_memories: list[str],
    project_slug: str,
) -> IndexingCoverage:
    cov = IndexingCoverage(
        min_facts=indexing_min_facts(),
        required_scenarios=indexing_required_scenarios(),
        min_outbound_deps=indexing_min_outbound_deps(),
    )
    for text in project_memories:
        if not is_countable_fact(text):
            continue
        cov.fact_count += 1
        cov.scenarios_found.update(parse_scenario_tags(text))
        cov.code_roles_found.update(parse_code_role_tags(text))
    cov.outbound_deps = count_outbound_links(topology_memories, project_slug)
    cov.compute_gaps()
    return cov


def load_project_memory_texts(db, project_user_id: str, *, top_k: int = 1000) -> list[str]:
    try:
        raw = db.get_all(filters={"user_id": project_user_id}, top_k=top_k)
    except Exception:
        return []
    rows = raw.get("results", []) if isinstance(raw, dict) else raw or []
    if not isinstance(rows, list):
        return []
    return [str(r.get("memory") or "") for r in rows if isinstance(r, dict)]


def load_topology_memory_texts(db, *, top_k: int = 2000) -> list[str]:
    try:
        raw = db.get_all(filters={"user_id": TOPOLOGY_ID}, top_k=top_k)
    except Exception:
        return []
    rows = raw.get("results", []) if isinstance(raw, dict) else raw or []
    if not isinstance(rows, list):
        return []
    return [str(r.get("memory") or "") for r in rows if isinstance(r, dict)]
