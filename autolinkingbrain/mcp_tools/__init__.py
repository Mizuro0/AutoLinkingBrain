"""Register all AutoLinkingBrain MCP tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from autolinkingbrain.mcp_context import McpContext
from autolinkingbrain.mcp_tools import health, indexing, knowledge, lifecycle, topology


def register_tools(mcp: FastMCP, mctx: McpContext) -> None:
    topology.register(mcp, mctx)
    indexing.register(mcp, mctx)
    health.register(mcp, mctx)
    knowledge.register(mcp, mctx)
    lifecycle.register(mcp, mctx)
