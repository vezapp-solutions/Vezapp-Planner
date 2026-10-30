# Deployment and production checklist

This describes what a production deployment of Vezapp Planner needs. Nothing here has been deployed yet; the demo runs locally (see the README).

## What runs

| Part | How |
|---|---|
| Database | PostgreSQL 16 (`docker-compose.yml` has a development instance). SQLite is for quick local work only. |
| API | Django under gunicorn or uvicorn behind an HTTPS reverse proxy. |
| Web | `next build` then `next start`, behind the same proxy. The proxy sends `/` to Next.js; Next.js forwards `/api/*` to Django (set `BACKEND_URL`). |

## Environment (`.env`, never committed)

| Variable | Production value |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | A random string of at least 32 characters. The app refuses to start with a shorter one or a `change-me` placeholder. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `DJANGO_ALLOWED_HOSTS` | Your domain(s), comma separated. |
| `COOKIE_SECURE` | `true` (the default when debug is off). |
| `SECURE_SSL_REDIRECT` | `true` (default). Set `false` only if the proxy already redirects http to https. |
| `SECURE_HSTS_SECONDS` | `31536000` (default). |
| `DB_ENGINE`, `POSTGRES_*` | `postgres` and the database credentials. |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Optional. Without a key the assistant runs in basic mode. |
| `ASSISTANT_MAX_TOKENS`, `ASSISTANT_DAILY_LIMIT` | Optional caps (800 and 200 by default). |
| `DEMO_PASSWORD` | Leave empty. `seed_demo` refuses to run unless `DJANGO_DEBUG=true`. |

## First deployment

1. Create the database and user; set the variables above.
2. `pip install -r backend/requirements.txt`, then `python manage.py migrate`.
3. Create the first Vezapp Admin with `python manage.py createsuperuser`-style tooling or the shell, and create each client company and its Company Admin from the Companies screen.
4. `npm ci && npm run build` in `frontend/`, then `npm start`.
5. Put both behind HTTPS. The proxy must set `X-Forwarded-Proto: https`.
6. Check `GET /api/v1/health` returns `{"status": "ok"}`.

## Security checklist

- [ ] `DJANGO_DEBUG=false` and a 32+ character secret key.
- [ ] HTTPS everywhere; HSTS on; cookies Secure.
- [ ] The database is not reachable from the internet; its password is not the development one.
- [ ] `.env` is not in the repository or the image.
- [ ] Demo users are not created in production. Remove any that exist.
- [ ] Backups of PostgreSQL, tested by restoring one.
- [ ] `pip-audit -r backend/requirements.txt` and `npm audit --omit=dev` are clean. They were on 30-10-2026 after Django REST framework moved to 3.18.
- [ ] Logs go somewhere that is kept; assistant questions are in the `AssistantLog` table and visible to admins at `/api/v1/assistant/logs`.

## Operating notes

- A plan of 500 lines takes about 3 seconds; refreshing the insights adds under 2.
- Plans and insight cards are derived data and can be rebuilt from the masters and schedule at any time. Back up the masters, schedule, scenarios and audit log first.
- The insight history keeps the last 60 runs per company; older ones are deleted automatically.
- The AI layer calls the Anthropic API from the server only. Prompts contain the question and tool results from that company's data; nothing else leaves the server.
