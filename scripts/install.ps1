# PLETHORA MJOLNIR - one-shot setup
# Creates a virtual environment, installs optional extractors, and writes a config.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
Set-Location $root

Write-Host "== PLETHORA MJOLNIR setup ==" -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv) ..."
    python -m venv .venv
}

$py = Join-Path $root ".venv\Scripts\python.exe"
Write-Host "Upgrading pip ..."
& $py -m pip install --quiet --upgrade pip

Write-Host "Installing optional extractors + watcher ..."
& $py -m pip install --quiet -r requirements.txt

Write-Host "Creating config ..."
& $py mj.py init

Write-Host ""
Write-Host "Done. Try:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe mj.py index"
Write-Host "  .\.venv\Scripts\python.exe mj.py search `"restaurant database schema`""
Write-Host "  .\.venv\Scripts\python.exe mj.py serve"
