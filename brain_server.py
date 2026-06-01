"""AutoLinkingBrain MCP server bootstrap."""

from __future__ import annotations

import os
import pathlib
import sys
import warnings
from datetime import datetime, timezone

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from autolinkingbrain.mcp_full_log import install_mcp_full_capture

install_mcp_full_capture(_REPO_ROOT)
warnings.filterwarnings("ignore")
os.environ.setdefault("MEM0_TELEMETRY", "false")

try:
    from mcp.server.fastmcp import FastMCP
    from mem0 import Memory

    from autolinkingbrain.mcp_constants import MCP_INSTRUCTIONS
    from autolinkingbrain.mcp_context import McpContext
    from autolinkingbrain.mcp_tools import register_tools
    from autolinkingbrain.mem0_settings import mem0_vector_config
except ImportError as e:
    with open(os.path.join(_REPO_ROOT, "critical_error.log"), "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] ImportError: {e}\n")
    raise SystemExit(1) from e

config = mem0_vector_config()
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    mem0_db = Memory.from_config(config_dict=config)

mcp = FastMCP("AutoLinkingBrain", instructions=MCP_INSTRUCTIONS)
_mctx = McpContext(db=mem0_db)
register_tools(mcp, _mctx)

if __name__ == "__main__":
    mcp.run()
