# Start Streamlit viewer (autostart / Task Scheduler friendly).
# Port: VIEWER_PORT env (default in .streamlit/config.toml). Repo: MEM0_SERVER_ROOT or parent of scripts/.
$ErrorActionPreference = "Stop"
$RepoRoot = if ($env:MEM0_SERVER_ROOT) {
    (Resolve-Path $env:MEM0_SERVER_ROOT).Path
} else {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
Set-Location $RepoRoot

$Streamlit = Join-Path $RepoRoot ".venv\Scripts\streamlit.exe"
if (-not (Test-Path -LiteralPath $Streamlit)) {
    Write-Error "Not found: $Streamlit (create venv and pip install -r requirements.txt)"
}

$viewer = Join-Path $RepoRoot "viewer.py"

# Override port: set VIEWER_PORT before launch.
if ($env:VIEWER_PORT) {
    $env:STREAMLIT_SERVER_PORT = "$env:VIEWER_PORT"
}
& $Streamlit run $viewer --browser.gatherUsageStats false
