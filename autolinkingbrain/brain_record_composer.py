"""Heuristic fact composer — English Mem0 bodies without LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_CODE_ROLE_RE = re.compile(
    r"\b(REST|SERVICE|DAO|REPO|CONTROLLER|CONFIG|INFRA|DTO|ENTITY|CLIENT|WORKER|TEST)\b",
    re.I,
)


@dataclass
class ComposedFact:
    tech: str
    scenario: str
    body: str
    code_role: str = ""

    def enriched(self) -> str:
        now = datetime.now(timezone.utc).isoformat()
        role = f" [ROLE:{self.code_role.upper()}]" if self.code_role else ""
        return f"[{self.tech.upper()}] [{self.scenario.upper()}]{role} (Updated: {now}): {self.body}"


def infer_code_role(path: str, content_hint: str = "") -> str:
    p = path.replace("\\", "/").lower()
    hint = (content_hint or "").upper()
    if "@RestController" in hint or "@Controller" in hint or "/api/" in p or "controller" in p:
        return "REST"
    if "repository" in p or "dao" in p or "Repository" in hint:
        return "DAO"
    if "service" in p or "@Service" in hint:
        return "SERVICE"
    if "config" in p or "@Configuration" in hint:
        return "CONFIG"
    if "dto" in p or "entity" in p or "@Entity" in hint:
        return "ENTITY"
    if "test" in p or p.endswith("test.kt") or p.endswith("test.java"):
        return "TEST"
    m = _CODE_ROLE_RE.search(hint)
    return m.group(1).upper() if m else "INFRA"


def infer_tech(path: str) -> str:
    p = path.lower()
    if p.endswith((".kt", ".kts")):
        return "kotlin"
    if p.endswith((".java",)):
        return "java"
    if p.endswith((".py",)):
        return "python"
    if p.endswith((".ts", ".tsx", ".js", ".jsx")):
        return "typescript"
    if p.endswith((".go",)):
        return "go"
    return "general"


def compose_entity_fact(
    *,
    path: str,
    summary: str,
    scenario: str = "architecture",
    tech: str = "",
    code_role: str = "",
    content_hint: str = "",
) -> ComposedFact:
    rel = Path(path).name
    role = code_role or infer_code_role(path, content_hint)
    t = tech or infer_tech(path)
    body = summary.strip() or f"Module/file `{rel}` at `{path}` — indexed for project analysis."
    return ComposedFact(tech=t, scenario=scenario, body=body, code_role=role)


def compose_api_contract(*, module: str, endpoints: list[str]) -> ComposedFact:
    lines = "; ".join(endpoints[:12])
    extra = f" (+{len(endpoints) - 12} more)" if len(endpoints) > 12 else ""
    body = f"Public API surface for `{module}`: {lines}{extra}."
    return ComposedFact(tech="general", scenario="api_contract", body=body, code_role="REST")


def compose_architecture_section(*, section: str, content: str, module: str = "") -> ComposedFact:
    prefix = f"Module `{module}` — " if module else ""
    body = f"{prefix}{section} architecture: {content.strip()[:2000]}"
    return ComposedFact(tech="general", scenario="architecture", body=body, code_role="SERVICE")
