# Vezapp Planner

Finite-capacity production planning for iron and steel sand-casting foundries, offered by Vezapp Solutions LLP to its clients. Multi-company (each foundry sees only its own data). Spec: [PROMPT.md](PROMPT.md).

**Status: Phases 0 to 6 are built (hardening and documentation included).** Login, roles, multi-company tenancy, audit trail, branded app shell, and the masters: company calendar, resources with availability and downtime, customers, parts and operation routes with explainable derived values, the monthly dispatch schedule with Excel and CSV upload, and the finite-capacity planning engine with estimated dispatch dates, bottlenecks, Gantt, load heatmap and printable plans, and what-if scenarios (block a resource, change a quantity or date, add an extra shift or overtime, see which lines move, then apply), ranked insight cards with a daily digest, reports (dispatch performance, utilisation, plan versus actual) with PDF and Excel export, a data-health screen, and an assistant that works in basic mode or with Claude. The security review, accessibility pass and performance checks of Phase 6 are done; see `docs/ARCHITECTURE.md` and `docs/DEPLOYMENT.md`.

## Requirements (Windows, PowerShell)

- Python 3.11 or newer (3.12 is the target; see `docs/ASSUMPTIONS.md`)
- Node.js 22 or newer
- Docker Desktop, for PostgreSQL. Optional: set `DB_ENGINE=sqlite` in `.env` to run without Docker.

## First run

```powershell
.\scripts\setup.ps1          # creates .env, Python venv, installs backend + frontend packages
.\scripts\dev.ps1 -Seed      # starts Postgres, migrates, seeds demo data, opens backend + frontend
```

Then open <http://localhost:3000>. The backend health check is <http://127.0.0.1:8000/api/v1/health>.

### Without Docker

Edit `.env` and set `DB_ENGINE=sqlite`, then run the same two commands. SQLite is for quick local development only; tests and production use PostgreSQL semantics.

### Demo users (synthetic data)

All demo users share the `DEMO_PASSWORD` from your `.env` (the example file sets one for local use). Demo data only seeds when `DJANGO_DEBUG=true`.

| Username | Role | Company |
|---|---|---|
| `vezapp.admin` | Vezapp Admin | all companies |
| `a.admin` | Company Admin | Demo Foundry A |
| `a.planner` | Planner | Demo Foundry A |
| `a.viewer` | Viewer | Demo Foundry A |
| `b.admin` | Company Admin | Demo Foundry B |
| `b.planner` | Planner | Demo Foundry B |

## Checks

```powershell
.\scripts\test.ps1              # ruff, pytest, eslint, tsc, vitest, next build
.\scripts\test.ps1 -SkipBuild   # faster
```

## Layout

```
backend/    Django 5 + DRF API  (apps/ core, accounts, companies; planning/ is the pure-Python engine)
frontend/   Next.js (App Router) + TypeScript + Tailwind
docs/       ASSUMPTIONS, OPEN_QUESTIONS, ARCHITECTURE, PLANNING_LOGIC, USER_GUIDE
scripts/    setup, dev, test, seed, brand_assets.py
```

## Configuration

Everything lives in `.env` (copy of `.env.example`; never committed). The product name is a single constant: `APP_NAME` in `backend/config/settings/base.py` and `NEXT_PUBLIC_APP_NAME` in the frontend. `ANTHROPIC_API_KEY` is optional and only used by the Phase 5 assistant.

## Branding

The logo (a transparent PNG, with only the empty margin trimmed) is copied from the supplied file into `frontend/public/brand/`. `scripts/brand_assets.py` regenerates the favicon and app icons from that copy and prints the sampled palette with contrast ratios.
