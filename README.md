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
`BOT_MODE=polling` (default) needs no public URL and is the simplest way to develop locally.

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
Before relying on this in production, read that doc's persistence note: the
free plan has no persistent disk, so SQLite data doesn't reliably survive
deploys/restarts.
