"""ArchitectureCurator MCP tools."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from autolinkingbrain.architecture_context import architecture_budget, build_module_context, get_architecture_doc_path
from autolinkingbrain.architecture_curator import section_status, update_section
from autolinkingbrain.architecture_doc import read_doc


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="getArchitectureDoc")
    async def get_architecture_doc(project_root: str = "") -> str:
        """Read docs/ARCHITECTURE.generated.md for project."""
        root = (project_root or os.getcwd()).strip()
        path = get_architecture_doc_path(root)
        return read_doc(path)

    @mcp.tool(name="updateArchitectureSection")
    async def update_architecture_section(
        section_id: str,
        content: str,
        project_root: str = "",
        project_slug: str = "",
        module: str = "",
    ) -> str:
        """Update one section (modules|apis|dataflow|integrations). English content."""
        root = (project_root or os.getcwd()).strip()
        return update_section(
            project_root=root,
            section_id=section_id,
            content=content,
            project_slug=project_slug,
            module=module,
        )

    @mcp.tool(name="getArchitectureBudget")
    async def get_architecture_budget() -> str:
        """Token/char budget hints for one-section-per-call workflow."""
        return json.dumps(architecture_budget(), indent=2)

    @mcp.tool(name="refreshArchitectureFromDiff")
    async def refresh_architecture_from_diff(project_root: str = "") -> str:
        """Report sections whose on-disk hash may be stale vs last write (MVP status)."""
        root = (project_root or os.getcwd()).strip()
        st = section_status(root)
        return json.dumps(st, indent=2)

    @mcp.tool(name="buildArchitectureContext")
    async def build_architecture_context(module_name: str, project_root: str = "") -> str:
        root = (project_root or os.getcwd()).strip()
        return build_module_context(module_name=module_name, project_root=root)
