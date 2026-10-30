# Every quality gate: ruff, pytest, eslint, tsc, vitest and a production build.
# Use -SkipBuild for a faster run.
param([switch]$SkipBuild)
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$python = "$root\backend\.venv\Scripts\python.exe"

function Step($name, $block) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name" -ForegroundColor Red; exit 1 }
}

Push-Location backend
Step "ruff"   { & $python -m ruff check . --exclude .venv }
Step "ruff format" { & $python -m ruff format --check . --exclude .venv }
Step "pytest" { & $python -m pytest }
Pop-Location

Push-Location frontend
Step "eslint"    { npm run lint }
Step "typecheck" { npm run typecheck }
Step "vitest"    { npm test }
if (-not $SkipBuild) { Step "next build" { npm run build } }
Pop-Location

Write-Host "`nAll checks passed." -ForegroundColor Green
