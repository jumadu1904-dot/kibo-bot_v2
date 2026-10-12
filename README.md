# Kibo Bot V2

Telegram productivity assistant (Google Calendar, Google Tasks, natural-language reminders, daily briefing).
See [docs/SCOPE.md](docs/SCOPE.md) for the features and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## Development
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows; use .venv/bin/python on Linux/macOS
cp .env.example .env                               # then set TELEGRAM_TOKEN
.venv/Scripts/python -m alembic upgrade head       # create the database
.venv/Scripts/python -m uvicorn kibo.main:app --app-dir src --reload
.venv/Scripts/python -m pytest
```
`BOT_MODE=polling` (default) needs no public URL for Telegram itself, but
connecting Google (Calendar + Tasks) still requires `PUBLIC_URL` — FastAPI
always serves `/oauth/google/callback` regardless of bot mode. For local
dev, `PUBLIC_URL=http://localhost:8000` plus the same redirect URI added to
your Google Cloud OAuth client's Authorized redirect URIs is enough (Google
allows plain `http://localhost` for "Web application" clients). See
`.env.example` for `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `ENCRYPTION_KEY`
and `STATE_SECRET` generation notes.

## Deployment (Render, not yet done)
Production always runs `BOT_MODE=webhook`, since Render's free plan sleeps the
service after 15 minutes without HTTP traffic — an internal polling loop or
timer wouldn't survive that. `render.yaml` describes the service (build with
`requirements.txt`, since that's what Render expects; it's generated from
`pyproject.toml`'s production dependencies — regenerate after changing them).

An external cron (cron-job.org, every 5 minutes) must call
`GET /check-reminders?token=<CRON_SECRET>` — that's what replaces in-process
scheduling for reminders and the daily briefing (see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#planificador-cron-extern-en-lloc-de-temporitzadors-interns)).

The free plan also has no persistent disk, so the database is **Neon**
(Postgres, free forever) instead of SQLite. Create a project at
[neon.tech](https://neon.tech), then set on Render:
```
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>/<db>?ssl=require
```
Locally, SQLite stays the default (`.env.example`) so development needs no
external service.
