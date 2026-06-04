#!/usr/bin/env python3
"""Migrate [CURSOR]/[AUT_LOG]/[TOOL_LOG] rows from Chroma to .cursor/autolog.db."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autolinkingbrain.migrate_autolog import run_migrate

if __name__ == "__main__":
    raise SystemExit(run_migrate())
