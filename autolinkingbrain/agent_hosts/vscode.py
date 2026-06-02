"""VS Code MCP client paths (workspace-scoped MCP config)."""

from __future__ import annotations

from pathlib import Path

from autolinkingbrain.agent_hosts.cursor import CursorHost


class VscodeHost(CursorHost):
    name = "vscode"

    def mcp_json_path(self, *, scope: str, project_root: Path | None) -> Path:
        s = (scope or "global").strip().lower()
        if s == "global":
            return Path.home() / ".vscode" / "mcp.json"
        root = (project_root or Path.cwd()).expanduser().resolve()
        return root / ".vscode" / "mcp.json"
