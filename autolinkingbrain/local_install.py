"""Machine-local MCP install profile (YAML, gitignored).

Copy config/local/install.yaml.example → config/local/install.yaml and edit.
Used by brain.py install, setup, mcp install, and sync-agent (optional MCP refresh).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autolinkingbrain.paths import REPO_ROOT

_LOCAL_DIR = REPO_ROOT / "config" / "local"
_DEFAULT_FILE = _LOCAL_DIR / "install.yaml"
_EXAMPLE_FILE = _LOCAL_DIR / "install.yaml.example"

_VALID_PROFILES = frozenset({"minimal", "standard", "full"})


@dataclass(frozen=True)
class LocalInstallConfig:
    profile: str = "standard"
    mcp_scope: str = "global"
    host: str = "cursor"
    mcp_project_root: str = ""
    with_codegraph: str = "auto"  # true | false | auto
    sync_mcp_on_agent_sync: bool = True

    def resolve_with_codegraph(self) -> bool:
        raw = (self.with_codegraph or "auto").strip().lower()
        if raw in ("1", "true", "yes"):
            return True
        if raw in ("0", "false", "no"):
            return False
        return bool(shutil.which("codegraph"))


def local_install_path() -> Path:
    override = os.environ.get("BRAIN_LOCAL_INSTALL_YAML", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_FILE


def example_install_path() -> Path:
    return _EXAMPLE_FILE


def _parse_yaml_flat(text: str) -> dict[str, Any]:
    """Minimal YAML: top-level keys, optional two-space nested section."""
    root: dict[str, Any] = {}
    section: dict[str, Any] = root
    section_name = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  ") and section_name:
            sub = line.strip()
            if ":" in sub:
                k, v = sub.split(":", 1)
                section[k.strip()] = _coerce_yaml_value(v.strip())
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            section = {}
            root[section_name] = section
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        if not key:
            continue
        if not v.strip() and not line.startswith(" "):
            section_name = key
            section = {}
            root[section_name] = section
            continue
        section[key] = _coerce_yaml_value(v.strip())
    return root


def _coerce_yaml_value(val: str) -> Any:
    v = val.strip().strip('"').strip("'")
    if v.lower() in ("true", "yes", "on"):
        return True
    if v.lower() in ("false", "no", "off"):
        return False
    if v.isdigit():
        return int(v)
    return v


def load_local_install(*, path: Path | None = None) -> LocalInstallConfig | None:
    p = path or local_install_path()
    if not p.is_file():
        return None
    try:
        data = _parse_yaml_flat(p.read_text(encoding="utf-8"))
    except OSError:
        return None
    mcp = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
    prof = str(mcp.get("profile") or data.get("profile") or "standard").strip().lower()
    if prof not in _VALID_PROFILES:
        prof = "standard"
    scope = str(mcp.get("scope") or data.get("mcp_scope") or "global").strip() or "global"
    host = str(data.get("host") or "cursor").strip() or "cursor"
    proot = str(mcp.get("project_root") or data.get("mcp_project_root") or "").strip()
    wcg = str(data.get("with_codegraph") or "auto").strip().lower() or "auto"
    sync_mcp = data.get("sync_mcp_on_agent_sync")
    if sync_mcp is None:
        sync_mcp = data.get("install_mcp_on_sync", True)
    return LocalInstallConfig(
        profile=prof,
        mcp_scope=scope,
        host=host,
        mcp_project_root=proot,
        with_codegraph=wcg,
        sync_mcp_on_agent_sync=bool(sync_mcp),
    )


def resolve_profile(cli_profile: str | None) -> str:
    """CLI flag wins; else config/local/install.yaml; else standard."""
    if cli_profile is not None and str(cli_profile).strip():
        p = str(cli_profile).strip().lower()
        if p in _VALID_PROFILES:
            return p
    loc = load_local_install()
    if loc:
        return loc.profile
    return "standard"


def resolve_mcp_install_kwargs(
    *,
    profile: str | None = None,
    scope: str | None = None,
    project_root: str | None = None,
    host: str | None = None,
    with_codegraph: bool | None = None,
) -> dict[str, Any]:
    loc = load_local_install()
    prof = resolve_profile(profile)
    sc = scope if scope is not None and str(scope).strip() else (loc.mcp_scope if loc else "global")
    return {
        "profile": prof,
        "scope": sc or "global",
        "project_root": (
            project_root
            if project_root is not None and str(project_root).strip()
            else (loc.mcp_project_root if loc else "")
        )
        or "",
        "host": host if host is not None and str(host).strip() else (loc.host if loc else "cursor"),
        "with_codegraph": (
            with_codegraph
            if with_codegraph is not None
            else (loc.resolve_with_codegraph() if loc else bool(shutil.which("codegraph")))
        ),
    }


def apply_local_mcp_install() -> int:
    """Merge ~/.cursor/mcp.json from config/local/install.yaml."""
    from autolinkingbrain.brain_install import mcp_install

    kw = resolve_mcp_install_kwargs()
    return mcp_install(
        scope=kw["scope"],
        project_root=kw["project_root"],
        profile=kw["profile"],
        host=kw["host"],
    )


def local_install_status_line() -> str:
    loc = load_local_install()
    if not loc:
        return f"local install: (none) — copy {example_install_path().name} → {local_install_path().name}"
    return (
        f"local install: profile={loc.profile} scope={loc.mcp_scope} "
        f"codegraph={loc.with_codegraph} sync_mcp={loc.sync_mcp_on_agent_sync} "
        f"({local_install_path()})"
    )
