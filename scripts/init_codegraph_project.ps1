# Initialize CodeGraph in one repo (wrapper around brain.py).
# Usage:
#   cd D:\your-project
#   powershell -File .\scripts\init_codegraph_project.ps1
#   powershell -File .\scripts\init_codegraph_project.ps1 -ProjectRoot D:\other-repo
param(
    [string]$ProjectRoot = (Get-Location).Path,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = if ($env:MEM0_SERVER_ROOT) {
    (Resolve-Path $env:MEM0_SERVER_ROOT).Path
} else {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
$args = @("codegraph", "init", "--no-default", $ProjectRoot)
if ($Force) { $args += "--force" }
& $Python (Join-Path $RepoRoot "brain.py") @args
