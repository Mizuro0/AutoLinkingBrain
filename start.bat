@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

REM No args -> setup + viewer. Other commands pass through (status, codegraph, setup, install…)
if "%~1"=="" (
  "%PY%" brain.py start
) else (
  "%PY%" brain.py %*
)

if errorlevel 1 (
  echo.
  echo Failed. See errors above.
  pause
  exit /b 1
)
endlocal
