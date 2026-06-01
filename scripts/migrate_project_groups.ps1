param(
    [string[]]$SourceSlugs = @(),
    [string[]]$Targets = @(),
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

if ($SourceSlugs.Count -eq 0 -or $Targets.Count -eq 0) {
    Write-Host @"
Usage: migrate_project_groups.ps1 -SourceSlugs <old> -Targets <slug...> [-Apply]

Example (dry-run):
  .\scripts\migrate_project_groups.ps1 -SourceSlugs old_monolith -Targets backend,frontend

Apply:
  .\scripts\migrate_project_groups.ps1 -SourceSlugs old_monolith -Targets backend,frontend -Apply
"@
    exit 1
}

# Mem0 OSS telemetry hits PostHog; disable when DNS/firewall blocks us.i.posthog.com.
if (-not $env:MEM0_TELEMETRY) {
    $env:MEM0_TELEMETRY = "false"
}

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "scripts\migrate_project_memories.py"

if (-not (Test-Path $python)) {
    throw "Python venv not found: $python"
}

if (-not (Test-Path $script)) {
    throw "Migration script not found: $script"
}

foreach ($source in $SourceSlugs) {
    $commonArgs = @(
        $script,
        "--source-slug", $source,
        "--targets"
    ) + $Targets + @(
        "--export-ambiguous", ".cursor\migration_ambiguous_${source}.jsonl"
    )

    Write-Host "== Dry-run ($source) =="
    & $python @commonArgs --dry-run
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "Dry-run only. To apply migration run:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\migrate_project_groups.ps1 -Apply"
    exit 0
}

Write-Host ""
Write-Host "== Apply migration =="
foreach ($source in $SourceSlugs) {
    $commonArgs = @(
        $script,
        "--source-slug", $source,
        "--targets"
    ) + $Targets + @(
        "--export-ambiguous", ".cursor\migration_ambiguous_${source}.jsonl"
    )

    Write-Host "-- Applying source: $source"
    & $python @commonArgs
}

Write-Host ""
Write-Host "Done. Source records are kept; review then clean manually if needed."
