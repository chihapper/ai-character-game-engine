# Launch the Real-Time AI Character Engine on Windows (PowerShell).
# Usage:  ./run.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "No .env found. Copy .env.example to .env and add your API keys." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from template — edit it, then re-run ./run.ps1" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt
Write-Host "Starting server on http://127.0.0.1:8000 ..." -ForegroundColor Green
& $py -m orchestrator.main
