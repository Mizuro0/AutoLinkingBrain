"""Cursor IDE paths."""

from __future__ import annotations

from pathlib import Path

from autolinkingbrain.agent_hosts.base import HostPaths
from autolinkingbrain.paths import REPO_ROOT


class CursorHost(HostPaths):
    name = "cursor"

    def mcp_json_path(self, *, scope: str, project_root: Path | None) -> Path:
        s = (scope or "global").strip().lower()
        if s == "project":
            root = (project_root or Path.cwd()).expanduser().resolve()
            return root / ".cursor" / "mcp.json"
        return Path.home() / ".cursor" / "mcp.json"

    def hooks_json_path(self) -> Path | None:
        return Path.home() / ".cursor" / "hooks.json"

    def events_path(self, *, repo_root: Path | None) -> Path:
        root = repo_root or REPO_ROOT
        return root / ".cursor" / "brain_events.jsonl"

    def skills_dir(self) -> Path | None:
        return Path.home() / ".cursor" / "skills"
