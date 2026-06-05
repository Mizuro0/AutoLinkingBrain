"""CLI host — no MCP json; events under XDG."""

from __future__ import annotations

import os
from pathlib import Path

from autolinkingbrain.agent_hosts.base import HostPaths
from autolinkingbrain.paths import REPO_ROOT


class CliHost(HostPaths):
    name = "cli"

    def mcp_json_path(self, *, scope: str, project_root: Path | None) -> Path:
        root = (project_root or Path.cwd()).expanduser().resolve()
        return root / ".brain" / "mcp.cli.json"

    def hooks_json_path(self) -> Path | None:
        return None

    def events_path(self, *, repo_root: Path | None) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", str(Path.home()))) / "autolinkingbrain"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "autolinkingbrain"
        return base / "events.jsonl" if repo_root is None else repo_root / ".brain" / "events.jsonl"

    def skills_dir(self) -> Path | None:
        return None
