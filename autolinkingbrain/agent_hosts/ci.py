"""CI host — same as CLI, events to workspace .brain/."""

from __future__ import annotations

from pathlib import Path

from autolinkingbrain.agent_hosts.cli import CliHost


class CiHost(CliHost):
    name = "ci"

    def events_path(self, *, repo_root: Path | None) -> Path:
        from autolinkingbrain.paths import REPO_ROOT

        root = repo_root or REPO_ROOT
        return root / ".brain" / "ci_events.jsonl"
