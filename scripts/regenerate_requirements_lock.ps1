# Regenerate requirements-lock.txt from requirements.txt + requirements-dev.txt
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Tmp = Join-Path $env:TEMP "alb-lock-venv-regen"
if (Test-Path $Tmp) { Remove-Item -Recurse -Force $Tmp }
python -m venv $Tmp
& "$Tmp\Scripts\pip.exe" install -q -r "$Root\requirements.txt" -r "$Root\requirements-dev.txt"
$lines = @(
    "# Locked transitive deps for CI and reproducible installs.",
    "# Regenerate: scripts/regenerate_requirements_lock.ps1",
    "# Install: pip install -r requirements-lock.txt",
    ""
)
$lines += & "$Tmp\Scripts\pip.exe" freeze | Where-Object { $_ -notmatch '^pywin32==' }
$out = Join-Path $Root "requirements-lock.txt"
$lines | Set-Content -Path $out -Encoding utf8
Write-Host "Wrote $out ($($lines.Count - 4) packages)"
Remove-Item -Recurse -Force $Tmp
