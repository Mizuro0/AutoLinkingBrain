"""Agent host adapters — resolve MCP/hooks/events paths per host."""

from __future__ import annotations

from pathlib import Path

from autolinkingbrain.agent_hosts.base import HostPaths
from autolinkingbrain.agent_hosts.cursor import CursorHost
from autolinkingbrain.agent_hosts.cli import CliHost
from autolinkingbrain.agent_hosts.ci import CiHost
from autolinkingbrain.agent_hosts.vscode import VscodeHost

_HOSTS = {
    "cursor": CursorHost(),
    "vscode": VscodeHost(),
    "cli": CliHost(),
    "ci": CiHost(),
    "auto": CursorHost(),
}


def resolve_host(kind: str = "auto") -> HostPaths:
    k = (kind or "auto").strip().lower()
    return _HOSTS.get(k, _HOSTS["cursor"])


def mcp_json_path(*, scope: str, project_root: Path | None, host_kind: str = "auto") -> Path:
    host = resolve_host(host_kind)
    return host.mcp_json_path(scope=scope, project_root=project_root)


def events_path(*, host_kind: str = "auto", repo_root: Path | None = None) -> Path:
    host = resolve_host(host_kind)
    return host.events_path(repo_root=repo_root)
