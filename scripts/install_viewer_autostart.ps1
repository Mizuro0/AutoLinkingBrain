# Creates a Startup shortcut: hidden PowerShell runs start_viewer.ps1 at logon.
# Run as normal user. To remove: delete "Mem0 Viewer.lnk" from shell:startup.
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startViewer = Join-Path $PSScriptRoot "start_viewer.ps1"
$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "Mem0 Viewer.lnk"

$Wsh = New-Object -ComObject WScript.Shell
$shortcut = $Wsh.CreateShortcut($lnkPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startViewer`""
$shortcut.WorkingDirectory = $RepoRoot
$shortcut.Description = "AutoLinkingBrain viewer"
$shortcut.Save()

Write-Host "Shortcut created: $lnkPath"
Write-Host "Log off/on or double-click the shortcut once to test."
