# Install a minimal Matt Pocock skill set for the MCP Triumvirate (not full catalog).
$ErrorActionPreference = "Stop"

$skills = @(
    "setup-matt-pocock-skills",
    "grill-with-docs",
    "tdd",
    "diagnose"
)

Write-Host "Installing Matt Pocock skills: $($skills -join ', ')"
Write-Host "Run /setup-matt-pocock-skills in Cursor once after install."
Write-Host ""

$npxArgs = @("--yes", "skills@latest", "add", "mattpocock/skills", "--skill") + $skills
& npx @npxArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
