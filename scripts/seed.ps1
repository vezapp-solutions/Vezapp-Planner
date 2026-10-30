# Create (or top up) the synthetic demo foundries and one user per role. Safe to re-run.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = "$root\backend\.venv\Scripts\python.exe"
Push-Location "$root\backend"
& $python manage.py migrate --noinput
& $python manage.py seed_demo
Pop-Location
