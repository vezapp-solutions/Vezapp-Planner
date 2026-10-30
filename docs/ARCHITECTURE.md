# Architecture

Vezapp Planner is a multi-tenant web application for production planning in sand-casting foundries. A Next.js front end talks to a Django REST API; a pure-Python engine does the planning.

```
Browser ──► Next.js (App Router, port 3000) ──/api/*──► Django + DRF (port 8000) ──► PostgreSQL
                                                          │
                                                          ├─ planning/   pure-Python planning engine (no Django)
                                                          ├─ insights/   pure-Python insight rules (no Django)
                                                          └─ apps/*      models, services, API
```

The browser only ever sees one origin. Next.js proxies `/api/*` to Django, so the sign-in cookies are same-origin and no CORS is needed.

## Repository layout

| Path | What it holds |
|---|---|
| `backend/planning/` | The planning engine. Pure functions over plain dataclasses: timeline, capacity ledger, requirement explosion, forward and backward pass, bottlenecks, what-if changes and diff. No imports from Django, so every rule is testable with hand-built data. |
| `backend/insights/` | The Insight Engine, also pure: facts in, ranked cards out. Thresholds in `rules.py`. |
| `backend/apps/` | Django apps: the adapters between the database and the two engines, and the API. |
| `backend/seeds/` | The synthetic demo foundries (all names invented) and the section 7.5 worked example. |
| `backend/tests/` | pytest. About 800 tests including the worked example, every insight rule, security sweeps and query counts. |
| `frontend/app/` | Pages (App Router). `(app)` is the signed-in shell, `(auth)` the sign-in. |
| `frontend/components/` | Shared UI (`CrudScreen`, forms, tabs, explain popovers) and per-area components. |
| `frontend/lib/` | The API client, session store, formatting, and the helper functions that are unit-tested with vitest. |
| `docs/` | This file, `PLANNING_LOGIC.md` (every formula), `USER_GUIDE.md`, `ASSUMPTIONS.md`, `OPEN_QUESTIONS.md`, `DEPLOYMENT.md`. |

## Backend apps

| App | Responsibility |
|---|---|
| `core` | Tenancy base (`CompanyScopedModel`, `for_company`), `CompanyScopedViewSet`, role-matrix permissions, the append-only `AuditLog` and the `@audited` decorator. |
| `accounts` | `User` (role, company), cookie-carried JWT sign-in, refresh, sign-out, `/me`, user management. |
| `companies` | Company, plants, shifts, the weekly pattern, holidays, planning settings. |
| `resources` | Resources and types, downtime, extra shifts and overtime (`CapacityAdjustment`), availability. |
| `masters` | Customers, grades, parts, operation types and each part's route, including several steps of an operation such as machining and the choice of machines by type (`machines.py`). |
| `scheduler` | The monthly dispatch schedule, Excel and CSV upload with preview and error report. |
| `plans` | Builds the engine input from the masters, runs the engine, stores the result (lean tables), exports PDF and Excel, and serves the Machine shop view (`machine_shop.py`). |
| `scenarios` | What-if: a scenario is a list of changes, run twice through the engine and diffed; applying makes them real in one transaction. |
| `insights` | Collects facts, runs the Insight Engine after every plan run, stores runs and cards (history, trends), reports, data health. |
| `assistant` | The read-only tools, basic mode, the Claude loop (with conversation memory and one self-correction), follow-up suggestions, the number guard, rate limits and the question log. |

## How a plan is made

1. `plans/inputs.py` reads the company's masters and open schedule lines into a `PlanInput`. A fingerprint of everything read is kept to tell when a plan is out of date.
2. `planning.engine.run_plan` returns a `PlanResult` (per-line dates and status, allocations per shift, load per resource and shift, bottlenecks). It is deterministic.
3. `plans/service.py` stores it in lean tables (numbers as floats, plain SQL inserts for the biggest tables). 500 lines take about 3 seconds end to end.
4. `insights.service.refresh` then turns the stored plan into cards. A failure there never fails the plan.

What-if reuses step 2 with a changed copy of the input: `planning/whatif.apply_changes` returns a new `PlanInput` and `diff_results` compares two results.

## Rules of the data layer

- Every business model inherits `CompanyScopedModel`; every viewset inherits `CompanyScopedViewSet`. The company comes from the signed-in user, never from the request body. A Vezapp Admin has no company and acts for one client through the `X-Company-Id` header, accepted only by viewsets that opt in.
- Cross-company references are refused at the serializer (`CompanyPKField`). Another tenant's row is a 404, not a 403.
- Masters and schedules are audited (who, when, before, after). Derived data (plans, insight cards) is not audited per row; the plan itself is.
- Calculations are never done in the browser. Screens show server numbers, and a number's formula opens in a popover (`Traced`).

## Security model

See `DEPLOYMENT.md` for the checklist. In short:

- **Sign-in:** JWT in httpOnly, SameSite=Lax cookies (Secure in production). Access tokens last 15 minutes; refresh tokens rotate and are blacklisted on use and on sign-out. Sign-in is throttled.
- **CSRF:** a state-changing request authenticated by cookie must carry `X-VP-Client: web`. A cross-site form cannot send it, and there is no CORS.
- **Roles:** Vezapp Admin, Company Admin, Planner, Viewer, in one permission matrix (`core/permissions.py`). A generic test walks every route to prove anonymous callers get nothing, viewers never write, and one company never sees another's rows.
- **Uploads:** 5 MB and 5,000 rows, validated before anything is saved; spreadsheet cells are written as text so a value such as `=1+1` can never run.
- **The assistant:** read-only tools, company set by the server, arguments validated, no raw SQL, per-user rate limits, a token cap, a log of every question, and a number guard that blocks any number not in the tool results. Tool results are marked as data, not instructions.
- **Headers:** `X-Frame-Options: DENY`, `nosniff`, a strict referrer policy; in production HSTS and a content-security policy that allows no third-party origin.
- **Secrets:** the secret key must be at least 32 random characters in production or the app will not start. Keys live only in `.env`, which is never committed.

## Front end

- Next.js 16 App Router, TypeScript, Tailwind v4 with design tokens in `globals.css` (light and dark, both meeting WCAG AA contrast).
- `lib/api.ts`: one fetch wrapper with a silent refresh on 401 and the CSRF header; `lib/use-api.ts` for reads.
- Charts and the Gantt are hand-written SVG; the load heatmap always prints the percentage so colour is never the only signal.
- Every screen has loading, empty and error states and is checked at 375, 768 and 1440 px. Targets are at least 24 px, controls have labels, and the whole app is keyboard-usable.

## Testing and gates

`scripts/test.ps1` runs: ruff, ruff format check, pytest, eslint, tsc, vitest, `next build`. The mandatory test is the section 7.5 worked example (`backend/tests/test_engine.py`).
