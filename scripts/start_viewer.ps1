# Delegates to Brain Viewer (viewer_server.py via brain.py).
# Legacy Streamlit path removed — use requirements-legacy.txt + streamlit run viewer.py if needed.
$ErrorActionPreference = "Stop"
Write-Warning "start_viewer.ps1 now starts Brain Viewer (not Streamlit). For legacy UI: pip install -r requirements-legacy.txt; streamlit run viewer.py"
& (Join-Path $PSScriptRoot "start_brain_viewer.ps1") @args
