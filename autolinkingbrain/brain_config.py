"""Load ~/.config/autolinkingbrain/config.toml with workspace override and env wins."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - py310
    tomllib = None  # type: ignore


def _xdg_config_home() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "autolinkingbrain"
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg) / "autolinkingbrain"
    return Path.home() / ".config" / "autolinkingbrain"


def global_config_path() -> Path:
    override = os.environ.get("BRAIN_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_config_home() / "config.toml"


def workspace_config_path(project_root: Path | str | None) -> Path | None:
    if not project_root:
        return None
    p = Path(project_root).expanduser().resolve() / ".brain" / "config.toml"
    return p if p.is_file() else None


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _parse_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        return _parse_toml_minimal(path.read_text(encoding="utf-8"))
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _parse_toml_minimal(text: str) -> dict[str, Any]:
    """Minimal TOML subset for flat sections (py310 without tomllib)."""
    root: dict[str, Any] = {}
    section: dict[str, Any] = root
    section_name = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            section = {}
            root[section_name] = section
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if val.lower() == "true":
            section[key] = True
        elif val.lower() == "false":
            section[key] = False
        elif val.isdigit():
            section[key] = int(val)
        else:
            try:
                section[key] = float(val)
            except ValueError:
                section[key] = val
    return root


DEFAULTS: dict[str, Any] = {
    "profile": {"name": "standard"},
    "host": {"kind": "auto"},
    "mcp": {"scope": "global", "project_root": ""},
    "chroma": {"path": "", "collection": "graph_brain"},
    "ollama": {
        "enabled": True,
        "embed_model": "nomic-embed-text",
        "llm_enrich": False,
        "review_model": "qwen2.5-coder:7b",
    },
    "fleet": {"enabled": False, "url": "", "token": "", "push": False},
    "metrics": {"async": True, "local_viewer": True},
    "analysis": {"auto_run": True, "batch_size": 5},
}


@dataclass
class BrainConfig:
    profile: str = "standard"
    host_kind: str = "auto"
    mcp_scope: str = "global"
    mcp_project_root: str = ""
    chroma_path: str = ""
    chroma_collection: str = "graph_brain"
    ollama_enabled: bool = True
    embed_model: str = "nomic-embed-text"
    llm_enrich: bool = False
    review_model: str = "qwen2.5-coder:7b"
    fleet_enabled: bool = False
    fleet_url: str = ""
    fleet_token: str = ""
    fleet_push: bool = False
    metrics_async: bool = True
    analysis_auto_run: bool = True
    analysis_batch_size: int = 5
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def include_qwen(self) -> bool:
        return self.profile in ("standard", "full") and bool(self.review_model.strip())

    @property
    def include_arch_curator(self) -> bool:
        return self.profile == "full"

    def apply_to_environ(self) -> None:
        """Push config into os.environ where env not already set."""
        if self.chroma_path and not os.environ.get("MEM0_CHROMA_PATH"):
            os.environ["MEM0_CHROMA_PATH"] = self.chroma_path
        if self.chroma_collection and not os.environ.get("MEM0_CHROMA_COLLECTION"):
            os.environ["MEM0_CHROMA_COLLECTION"] = self.chroma_collection
        if not os.environ.get("OLLAMA_EMBED"):
            os.environ["OLLAMA_EMBED"] = self.embed_model
        if self.review_model and not os.environ.get("OLLAMA_REVIEW_MODEL"):
            os.environ["OLLAMA_REVIEW_MODEL"] = self.review_model
        if not self.llm_enrich:
            os.environ.setdefault("MEM0_AUTOLOG_USE_OLLAMA", "0")
        if self.metrics_async:
            os.environ.setdefault("MEM0_METRICS_ASYNC", "1")
        if self.fleet_enabled and self.fleet_push:
            os.environ.setdefault("BRAIN_FLEET_ENABLED", "1")
            if self.fleet_url:
                os.environ.setdefault("BRAIN_FLEET_URL", self.fleet_url)
            if self.fleet_token:
                os.environ.setdefault("BRAIN_FLEET_TOKEN", self.fleet_token)


def _from_merged(data: dict[str, Any]) -> BrainConfig:
    prof = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    host = data.get("host") if isinstance(data.get("host"), dict) else {}
    mcp = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
    chroma = data.get("chroma") if isinstance(data.get("chroma"), dict) else {}
    ollama = data.get("ollama") if isinstance(data.get("ollama"), dict) else {}
    fleet = data.get("fleet") if isinstance(data.get("fleet"), dict) else {}
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    return BrainConfig(
        profile=str(prof.get("name") or "standard"),
        host_kind=str(host.get("kind") or "auto"),
        mcp_scope=str(mcp.get("scope") or "global"),
        mcp_project_root=str(mcp.get("project_root") or ""),
        chroma_path=str(chroma.get("path") or ""),
        chroma_collection=str(chroma.get("collection") or "graph_brain"),
        ollama_enabled=bool(ollama.get("enabled", True)),
        embed_model=str(ollama.get("embed_model") or "nomic-embed-text"),
        llm_enrich=bool(ollama.get("llm_enrich", False)),
        review_model=str(ollama.get("review_model") or "qwen2.5-coder:7b"),
        fleet_enabled=bool(fleet.get("enabled", False)),
        fleet_url=str(fleet.get("url") or ""),
        fleet_token=str(fleet.get("token") or ""),
        fleet_push=bool(fleet.get("push", False)),
        metrics_async=bool(metrics.get("async", True)),
        analysis_auto_run=bool(analysis.get("auto_run", True)),
        analysis_batch_size=int(analysis.get("batch_size") or 5),
        raw=data,
    )


def load_config(*, project_root: Path | str | None = None) -> BrainConfig:
    merged = dict(DEFAULTS)
    gpath = global_config_path()
    if gpath.is_file():
        merged = _deep_merge(merged, _parse_toml(gpath))
    wpath = workspace_config_path(project_root)
    if wpath:
        merged = _deep_merge(merged, _parse_toml(wpath))
    cfg = _from_merged(merged)
    cfg.apply_to_environ()
    return cfg


def save_global_config(data: dict[str, Any]) -> Path:
    path = global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml(data), encoding="utf-8")
    return path


def _dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for k, v in values.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            else:
                lines.append(f'{k} = "{v}"')
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def init_default_config(*, profile: str = "standard", mcp_scope: str = "global", host_kind: str = "auto") -> Path:
    data = _deep_merge(dict(DEFAULTS), {
        "profile": {"name": profile},
        "host": {"kind": host_kind},
        "mcp": {"scope": mcp_scope},
    })
    return save_global_config(data)
