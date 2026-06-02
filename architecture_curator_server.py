"""ArchitectureCurator MCP server bootstrap."""

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

    from autolinkingbrain.brain_config import load_config
    from autolinkingbrain.mcp_tools.architecture_tools import register as register_arch_tools
except ImportError as e:
    with open(os.path.join(_REPO_ROOT, "critical_error.log"), "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] ArchitectureCurator ImportError: {e}\n")
    raise SystemExit(1) from e

load_config()

_INSTRUCTIONS = """ArchitectureCurator — incremental docs/ARCHITECTURE.generated.md (one section per call).

Pair with AutoLinkingBrain for Mem0 facts and CodeGraph for structure.
Tools: getArchitectureDoc, updateArchitectureSection, getArchitectureBudget, refreshArchitectureFromDiff.
"""

mcp = FastMCP("ArchitectureCurator", instructions=_INSTRUCTIONS)
register_arch_tools(mcp)

if __name__ == "__main__":
    mcp.run()
