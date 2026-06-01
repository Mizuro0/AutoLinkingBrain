# AutoLinkingBrain — установка venv, глобальный MCP (Cursor) и хуки Mem0.
#
# Запуск из корня репозитория:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
#
# Опции:
#   -SkipVenv          не создавать venv / pip install
#   -SkipMcp            не трогать %USERPROFILE%\.cursor\mcp.json
#   -SkipHooks          не трогать %USERPROFILE%\.cursor\hooks.json
#   -SkipOllamaCheck    не проверять Ollama
#   -PullOllamaModels   ollama pull llama3.2 и nomic-embed-text (если ollama в PATH)
#   -WithCodeGraphMcp   добавить codegraph в mcp.json (если codegraph в PATH)
#
# MCP/hooks merge uses autolinkingbrain.brain_install (same as python brain.py install).
# Prefer: python brain.py install  — cross-platform, single source of truth.
#
#Requires -Version 5.1
param(
    [switch]$SkipVenv,
    [switch]$SkipMcp,
    [switch]$SkipHooks,
    [switch]$SkipOllamaCheck,
    [switch]$PullOllamaModels,
    [switch]$WithCodeGraphMcp
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$BrainServer = Join-Path $RepoRoot "brain_server.py"
$Requirements = Join-Path $RepoRoot "requirements.txt"
$HookSession = Join-Path $RepoRoot ".cursor\hooks\session_mem0_bootstrap.py"
$HookAutolog = Join-Path $RepoRoot ".cursor\hooks\mem0_autolog_after_response.py"
$HookPostTool = Join-Path $RepoRoot ".cursor\hooks\mem0_autolog_post_tool.py"

$CursorDir = Join-Path $env:USERPROFILE ".cursor"
$McpJsonPath = Join-Path $CursorDir "mcp.json"
$HooksJsonPath = Join-Path $CursorDir "hooks.json"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-SystemPython {
    foreach ($cmd in @("python", "py")) {
        try {
            $exe = Get-Command $cmd -ErrorAction Stop
            if ($cmd -eq "py") {
                $ver = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                if ($LASTEXITCODE -ne 0) { continue }
                return @{ Command = "py"; Args = @("-3"); Version = $ver }
            }
            $ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            return @{ Command = $exe.Source; Args = @(); Version = $ver }
        } catch {
            continue
        }
    }
    return $null
}

function Test-PythonVersion([string]$Version) {
    $parts = $Version.Split(".")
    if ($parts.Count -lt 2) { return $false }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 10)
}

function Invoke-BrainInstallMerge {
    param(
        [string]$Python,
        [switch]$SkipMcp,
        [switch]$SkipHooks,
        [switch]$WithCodeGraph
    )
    $code = @"
import sys
from pathlib import Path
sys.path.insert(0, r'$RepoRoot')
from autolinkingbrain.brain_install import merge_cursor_config
merge_cursor_config(
    Path(r'$Python'),
    skip_mcp=$($SkipMcp.IsPresent),
    skip_hooks=$($SkipHooks.IsPresent),
    with_codegraph=$($WithCodeGraph.IsPresent),
)
"@
    & $Python -c $code
    if ($LASTEXITCODE -ne 0) { throw "merge_cursor_config failed (exit $LASTEXITCODE)" }
}

function Test-OllamaReachable {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Show-CodeGraphGuide {
    Write-Host ""
    Write-Host '--- CodeGraph (companion MCP, install separately) ---' -ForegroundColor Yellow
    Write-Host '  Step 1: Global install once in PowerShell:' -ForegroundColor DarkGray
    Write-Host '       irm https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1 | iex' -ForegroundColor DarkGray
    Write-Host '     alt: npm i -g @colbymchenry/codegraph' -ForegroundColor DarkGray
    Write-Host '  Step 2: Per project:' -ForegroundColor DarkGray
    Write-Host '       cd your-project-folder' -ForegroundColor DarkGray
    Write-Host '       codegraph init -i' -ForegroundColor DarkGray
    Write-Host '  Step 3: Reload Cursor; verify with: codegraph status' -ForegroundColor DarkGray
    Write-Host '  Step 4: Re-run install.ps1 -WithCodeGraphMcp if codegraph is on PATH' -ForegroundColor DarkGray
    Write-Host '  Roles: CodeGraph = code structure | AutoLinkingBrain = memory + cross-repo links' -ForegroundColor DarkGray
}

Write-Host "AutoLinkingBrain installer" -ForegroundColor Green
Write-Host "Repo: $RepoRoot"

# --- Python / venv ---
if (-not $SkipVenv) {
    Write-Step "Python venv + dependencies"
    $sysPy = Get-SystemPython
    if ($null -eq $sysPy) {
        throw "Python 3.10+ not found. Install from https://www.python.org/downloads/ and retry."
    }
    if (-not (Test-PythonVersion $sysPy.Version)) {
        throw "Python $($sysPy.Version) found; need 3.10+."
    }
    Write-Host "  system Python: $($sysPy.Version)"

    if (-not (Test-Path $PythonExe)) {
        Write-Host "  creating venv..."
        if ($sysPy.Command -eq "py") {
            & py -3 -m venv $VenvDir
        } else {
            & $sysPy.Command -m venv $VenvDir
        }
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed (exit $LASTEXITCODE)" }
    }

    if (-not (Test-Path $PipExe)) { throw "pip not found in venv: $PipExe" }

    Write-Host "  pip install -r requirements.txt ..."
    & $PipExe install -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
} else {
    Write-Step "Skip venv (-SkipVenv)"
}

if (-not (Test-Path $PythonExe)) { throw "Missing venv python: $PythonExe - run without -SkipVenv" }
if (-not (Test-Path $BrainServer)) { throw "Missing brain_server.py: $BrainServer" }
if (-not (Test-Path $HookSession)) { throw "Missing hook: $HookSession" }
if (-not (Test-Path $HookAutolog)) { throw "Missing hook: $HookAutolog" }
if (-not (Test-Path $HookPostTool)) { throw "Missing hook: $HookPostTool" }

# --- Ollama ---
if (-not $SkipOllamaCheck) {
    Write-Step "Ollama check"
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaCmd) {
        Write-Host '  ! ollama not in PATH - autolog/embeddings need it: https://ollama.com/download' -ForegroundColor Yellow
    } elseif (Test-OllamaReachable) {
        Write-Host "  OK: Ollama API http://127.0.0.1:11434" -ForegroundColor Green
        if ($PullOllamaModels) {
            foreach ($model in @("llama3.2", "nomic-embed-text")) {
                Write-Host "  ollama pull $model ..."
                & ollama pull $model
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "  ! ollama pull $model failed (exit $LASTEXITCODE)" -ForegroundColor Yellow
                }
            }
        }
    } else {
        Write-Host '  ! ollama in PATH but API not reachable - run: ollama serve' -ForegroundColor Yellow
    }
}

# --- MCP + hooks (brain_install — includes MEM0_TELEMETRY=false) ---
if (-not $SkipMcp -or -not $SkipHooks) {
    Write-Step "Merge Cursor config (brain_install)"
    if (-not $SkipMcp) { Write-Host "  -> $McpJsonPath" }
    if (-not $SkipHooks) { Write-Host "  -> $HooksJsonPath" }
    Invoke-BrainInstallMerge -Python $PythonExe -SkipMcp:$SkipMcp -SkipHooks:$SkipHooks -WithCodeGraph:$WithCodeGraphMcp
    Write-Host '  AutoLinkingBrain entry updated (cwd=${workspaceFolder}, MEM0_TELEMETRY=false)' -ForegroundColor Green
} else {
    Write-Step "Skip MCP and hooks (-SkipMcp -SkipHooks)"
}

# --- Done ---
Write-Step "Done"
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "  1. Developer: Reload Window in Cursor" -ForegroundColor Green
Write-Host '  2. Settings -> MCP - confirm AutoLinkingBrain is green' -ForegroundColor Green
Write-Host '  3. New Agent session - sessionStart injects Mem0 context' -ForegroundColor Green
Write-Host "  4. Optional viewer: .\scripts\start_brain_viewer.ps1 -> http://127.0.0.1:8501/" -ForegroundColor Green
Write-Host "Re-run install.ps1 after moving the repo to refresh paths in mcp.json / hooks.json" -ForegroundColor Green

Show-CodeGraphGuide
