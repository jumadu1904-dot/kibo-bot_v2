from fastapi import FastAPI
from fastapi.testclient import TestClient

from kibo.web import routes
from kibo.web.routes import router


class _FakeUser:
    def __init__(self, telegram_id, lang="en", onboarding_step="google"):
        self.telegram_id = telegram_id
        self.lang = lang
        self.onboarding_step = onboarding_step


class _FakeBotInner:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text))


class _FakeApplication:
    def __init__(self):
        self.bot = _FakeBotInner()


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.bot = _FakeApplication()
    return app


def test_missing_code_or_state_returns_400():
    client = TestClient(_make_app())
    resp = client.get("/oauth/google/callback", params={"state": "s"})
    assert resp.status_code == 400


def test_google_error_param_returns_400():
    client = TestClient(_make_app())
    resp = client.get("/oauth/google/callback", params={"error": "access_denied"})
    assert resp.status_code == 400


def test_invalid_state_returns_400(monkeypatch):
    async def fake_handle_callback(session, *, code, state):
        return None

    monkeypatch.setattr(routes.google_auth, "handle_callback", fake_handle_callback)

    client = TestClient(_make_app())
    resp = client.get("/oauth/google/callback", params={"code": "c", "state": "bad"})
    assert resp.status_code == 400


def test_successful_callback_sends_telegram_message_and_advances_onboarding(monkeypatch):
    user = _FakeUser(telegram_id=42)

    async def fake_handle_callback(session, *, code, state):
        return 42

    async def fake_get_by_telegram_id(session, telegram_id):
        return user

    async def fake_advance_step(session, user_, step):
        user_.onboarding_step = step
        return user_

    monkeypatch.setattr(routes.google_auth, "handle_callback", fake_handle_callback)
    monkeypatch.setattr(routes.users_repo, "get_by_telegram_id", fake_get_by_telegram_id)
    monkeypatch.setattr(routes.onboarding_service, "advance_step", fake_advance_step)

    app = _make_app()
    client = TestClient(app)
    resp = client.get("/oauth/google/callback", params={"code": "c", "state": "s"})

    assert resp.status_code == 200
    assert user.onboarding_step == "done"
    assert app.state.bot.bot.sent == [(42, "✅ Google connected! You can now see your agenda and tasks.")]
