# Option A: paste into $PROFILE and set MEM0_SERVER_ROOT to your repo path.
# Option B: dot-source from repo (PSScriptRoot must be this scripts folder):
#   . D:\mcp_server\scripts\viewer_profile_snippet.ps1
$env:MEM0_SERVER_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
function mem0v {
    param([switch]$Run)
    $root = $env:MEM0_SERVER_ROOT
    $hostName = if ($env:MEM0_VIEWER_HOST) { $env:MEM0_VIEWER_HOST } else { "mem0viewer" }
    $port = if ($env:VIEWER_PORT) { $env:VIEWER_PORT } else { "8501" }
    if ($Run) {
        & "$root\scripts\start_viewer.ps1"
    } else {
        Start-Process "http://${hostName}:$port/"
    }
}
