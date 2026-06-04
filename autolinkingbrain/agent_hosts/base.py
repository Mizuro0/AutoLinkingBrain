"""Base host adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class HostPaths(ABC):
    name: str = "base"

    @abstractmethod
    def mcp_json_path(self, *, scope: str, project_root: Path | None) -> Path:
        ...

    @abstractmethod
    def hooks_json_path(self) -> Path | None:
        ...

    @abstractmethod
    def events_path(self, *, repo_root: Path | None) -> Path:
        ...

    @abstractmethod
    def skills_dir(self) -> Path | None:
        ...
