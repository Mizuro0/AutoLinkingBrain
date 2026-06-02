# Pilot workflow: backend (D:\codes\backend)
# Run after deploy from mcp_server repo.

$Backend = "D:\codes\backend"
$Brain = "D:\mcp_server"

Set-Location $Brain
& .\.venv\Scripts\python.exe brain.py gc audit --project-root $Backend
# Review output; purge autolog with confirm token if needed:
# & .\.venv\Scripts\python.exe brain.py gc purge --confirm-token TOKEN --apply --project-root $Backend

& .\.venv\Scripts\python.exe brain.py analyze auto --project-root $Backend --batch-size 10
# Repeat analyze until remaining~0 or use without --once in CLI (loops until done)

& .\.venv\Scripts\python.exe brain.py health --project-root $Backend
# Verify ANALYSIS STATUS ok, COVERAGE sufficient, then markIndexingComplete via Cursor MCP

Write-Host "Architecture sections: use ArchitectureCurator MCP updateArchitectureSection for modules/apis"
Write-Host "Expected artifact: $Backend\docs\ARCHITECTURE.generated.md"
