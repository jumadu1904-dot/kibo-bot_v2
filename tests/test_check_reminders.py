import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kibo.web.routes import router


class _FakeSettings:
    webhook_secret = ""
    cron_secret = "s3cr3t"


class _FakeBot:
    pass


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.settings = _FakeSettings()
    app.state.bot = _FakeBot()
    app.state.reminders_lock = asyncio.Lock()
    return app


def test_rejects_wrong_token():
    client = TestClient(_make_app())
    resp = client.get("/check-reminders", params={"token": "wrong"})
    assert resp.status_code == 403


def test_accepts_correct_token_and_queues(monkeypatch):
    called = asyncio.Event()

    async def fake_run_due_checks(bot):
        called.set()

    monkeypatch.setattr("kibo.services.reminders_cron.run_due_checks", fake_run_due_checks)

    client = TestClient(_make_app())
    resp = client.get("/check-reminders", params={"token": "s3cr3t"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "status": "queued"}


def test_skips_when_already_running():
    app = _make_app()
    app.state.reminders_lock._locked = True  # simulate a run in progress

    async def _acquire_forever():
        return

    # Force `.locked()` to report True without needing a real coroutine holding it.
    app.state.reminders_lock.acquire = lambda: asyncio.sleep(0)  # not awaited/used directly
    app.state.reminders_lock.locked = lambda: True

    client = TestClient(app)
    resp = client.get("/check-reminders", params={"token": "s3cr3t"})
    assert resp.json() == {"ok": True, "status": "skipped_already_running"}
