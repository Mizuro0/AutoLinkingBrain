param(
    [string[]]$SourceSlugs = @("gemini_filters", "gemini_marking"),
    [string[]]$Targets = @("backend", "crm_server", "vet_pathomorphology", "reference_client", "reference_service"),
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

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
