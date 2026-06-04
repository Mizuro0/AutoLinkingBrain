#!/usr/bin/env bash
# Install a minimal Matt Pocock skill set for the MCP Triumvirate (not full catalog).
set -euo pipefail

SKILLS=(
  setup-matt-pocock-skills
  grill-with-docs
  tdd
  diagnose
)

echo "Installing Matt Pocock skills: ${SKILLS[*]}"
echo "Run /setup-matt-pocock-skills in Cursor once after install."
echo ""

npx --yes skills@latest add mattpocock/skills --skill "${SKILLS[@]}"
