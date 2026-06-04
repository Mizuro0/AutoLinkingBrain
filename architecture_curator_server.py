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

_INSTRUCTIONS = """ArchitectureCurator — local Ollama (Qwen) module architect + handoff for the host agent.

Workflow (one module at a time — small model):
1. getArchitectProtocol
2. planArchitectureRun { modules: ["feature-a", "feature-b"] }
3. Per module: Brain recall + CodeGraph → runArchitectModule { module, context, section_focus }
4. getArchitectHandoff → READ artifact_path (docs/architecture/modules/<slug>.md)
5. recordAgentArchitectureReview { agent_notes, agent_status, resolved_questions }
6. rollupArchitectureModule when done; storeKnowledge (Brain)

Signals: .brain/architecture/handoff.json (signal=module_ready).
Do NOT loop runArchitectModule for all modules in one turn — process sequentially with agent review.
Legacy: updateArchitectureSection, getArchitectureDoc.
"""

mcp = FastMCP("ArchitectureCurator", instructions=_INSTRUCTIONS)
register_arch_tools(mcp)

if __name__ == "__main__":
    mcp.run()
