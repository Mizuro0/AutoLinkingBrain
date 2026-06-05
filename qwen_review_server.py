"""Qwen Reviewer MCP server bootstrap (separate from AutoLinkingBrain)."""

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
os.environ.setdefault("OLLAMA_REVIEW_MODEL", "qwen2.5-coder:7b")

try:
    from mcp.server.fastmcp import FastMCP
    from mem0 import Memory

    from autolinkingbrain.mcp_context import McpContext
    from autolinkingbrain.mcp_tools.review_tools import register as register_review_tools
    from autolinkingbrain.mem0_settings import mem0_vector_config
except ImportError as e:
    with open(os.path.join(_REPO_ROOT, "critical_error.log"), "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] QwenReviewer ImportError: {e}\n")
    raise SystemExit(1) from e

_REVIEW_INSTRUCTIONS = """Qwen Reviewer — local Ollama code review with Mem0 contracts and CodeGraph impact.

Use for diff/staged review only (not memory writes). Pair with AutoLinkingBrain for indexed contracts.
Tools: reviewDiff, reviewStaged, getReviewBudget. Output: Russian markdown findings.
"""

config = mem0_vector_config()
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    mem0_db = Memory.from_config(config_dict=config)

mcp = FastMCP("QwenReviewer", instructions=_REVIEW_INSTRUCTIONS)
_mctx = McpContext(db=mem0_db)
register_review_tools(mcp, _mctx)

if __name__ == "__main__":
    mcp.run()
