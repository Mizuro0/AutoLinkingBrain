# Start Brain viewer — delegates to brain.py (no PowerShell logic required).
$ErrorActionPreference = "Stop"
$RepoRoot = if ($env:MEM0_SERVER_ROOT) {
    (Resolve-Path $env:MEM0_SERVER_ROOT).Path
} else {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
Set-Location $RepoRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
& $Python (Join-Path $RepoRoot "brain.py") start @args
