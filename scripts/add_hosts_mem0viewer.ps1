# Adds: 127.0.0.1 mem0viewer  -> use http://mem0viewer:8501/
# Run elevated: right-click PowerShell -> Run as administrator.
$ErrorActionPreference = "Stop"
$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$marker = "# autolinkingbrain mem0viewer"
$line = "127.0.0.1 mem0viewer $marker"
$content = Get-Content -LiteralPath $hostsPath -Raw -Encoding Default
if ($content -match "mem0viewer") {
    Write-Host "hosts already contains mem0viewer."
    exit 0
}
Add-Content -LiteralPath $hostsPath -Value "`r`n$line" -Encoding Ascii
Write-Host "Added line: $line"
