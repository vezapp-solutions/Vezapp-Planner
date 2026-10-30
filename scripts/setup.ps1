# One-time setup: .env, Python virtualenv + packages, npm packages.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example (edit it if you want different values)."
}

if (-not (Test-Path backend\.venv)) {
    Write-Host "Creating Python virtualenv..."
    python -m venv backend\.venv
}
& backend\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& backend\.venv\Scripts\python.exe -m pip install --quiet -r backend\requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Push-Location frontend
npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed" }
Pop-Location

Write-Host ""
Write-Host "Setup done. Next:  .\scripts\dev.ps1 -Seed"
