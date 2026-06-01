#!/usr/bin/env python3
"""CLI wrapper: sync memory_cross_links.json into Mem0 (see autolinkingbrain/cross_link_mem0_sync.py)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from autolinkingbrain.cross_link_mem0_sync import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
