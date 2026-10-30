# Start everything for local development: Postgres (Docker, unless DB_ENGINE=sqlite),
# migrations, Django on :8000 and Next.js on :3000, each in its own window.
param([switch]$Seed)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Get-EnvValue($name, $default) {
    if (Test-Path .env) {
        $line = Select-String -Path .env -Pattern "^\s*$name\s*=\s*(.*)$" | Select-Object -First 1
        if ($line) { return $line.Matches[0].Groups[1].Value.Trim() }
    }
    return $default
}

$python = "$root\backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Run .\scripts\setup.ps1 first." }

if ((Get-EnvValue "DB_ENGINE" "postgres") -eq "postgres") {
    Write-Host "Starting PostgreSQL (docker compose)..."
    docker compose up -d --wait db
    if ($LASTEXITCODE -ne 0) {
        throw "Docker/Postgres did not start. Start Docker Desktop, or set DB_ENGINE=sqlite in .env."
    }
}

Push-Location backend
& $python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "migrate failed" }
if ($Seed) { & $python manage.py seed_demo }
Pop-Location

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\backend'; & '$python' manage.py runserver 127.0.0.1:8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev"

Write-Host ""
Write-Host "Backend  http://127.0.0.1:8000/api/v1/health"
Write-Host "App      http://localhost:3000"
