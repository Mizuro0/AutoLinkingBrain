# Open viewer in default browser (short hostname after hosts edit; see README).
param(
    [string]$HostName = $(if ($env:MEM0_VIEWER_HOST) { $env:MEM0_VIEWER_HOST } else { "mem0viewer" }),
    [int]$Port = $(if ($env:VIEWER_PORT) { [int]$env:VIEWER_PORT } else { 8501 })
)
$url = "http://${HostName}:$Port/"
Start-Process $url
