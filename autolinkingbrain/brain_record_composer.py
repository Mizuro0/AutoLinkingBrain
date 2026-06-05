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


_SIGNAL_ROLES = frozenset({"REST", "SERVICE", "DAO", "CONTROLLER"})
_TYPE_NAME_RE = re.compile(r"(?:class|interface|object|enum)\s+(\w+)")


def extract_type_names(content_hint: str, *, limit: int = 6) -> list[str]:
    seen: list[str] = []
    for name in _TYPE_NAME_RE.findall(content_hint or ""):
        if name not in seen:
            seen.append(name)
        if len(seen) >= limit:
            break
    return seen


def extract_http_paths(content_hint: str, *, limit: int = 8) -> list[str]:
    paths: list[str] = []
    for m in re.finditer(r'@(?:Get|Post|Put|Delete|Patch)Mapping\s*\(\s*["\']([^"\']+)', content_hint or "", re.I):
        p = m.group(1).strip()
        if p and p not in paths:
            paths.append(p)
        if len(paths) >= limit:
            break
    return paths


def compose_file_signal(
    *,
    path: str,
    content_hint: str = "",
    code_role: str = "",
    tech: str = "",
) -> ComposedFact | None:
    """One curated Mem0 fact for a meaningful source file (REST/SERVICE/DAO), not a scan log."""
    role = (code_role or infer_code_role(path, content_hint)).upper()
    if role not in _SIGNAL_ROLES:
        return None
    rel = path.replace("\\", "/")
    names = extract_type_names(content_hint)
    if not names:
        return None
    endpoints = extract_http_paths(content_hint) if role in ("REST", "CONTROLLER") else []
    parts = [f"`{rel}` defines {', '.join(names)} ({role})."]
    if endpoints:
        parts.append(f"HTTP mappings: {', '.join(endpoints[:6])}.")
    body = " ".join(parts)
    return ComposedFact(tech=tech or infer_tech(path), scenario="architecture", body=body, code_role=role)


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
