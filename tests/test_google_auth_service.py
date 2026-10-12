from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo import security
from kibo.clients.google_api import TokenResponse
from kibo.db.models import Base
from kibo.db.repositories import google_accounts, users
from kibo.services import google_auth


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


def test_get_authorization_url_embeds_valid_state():
    url = google_auth.get_authorization_url(777)
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert security.verify_state(state) == 777


async def test_is_connected_false_when_no_account(session: AsyncSession):
    user = await users.create(session, 1)
    assert await google_auth.is_connected(session, user) is False


async def test_handle_callback_stores_encrypted_refresh_token(session: AsyncSession, monkeypatch):
    user = await users.create(session, 42)
    state = security.sign_state(user.telegram_id)

    async def fake_exchange_code(**kwargs):
        return TokenResponse(access_token="acc", refresh_token="refresh-secret", expires_in=3600, scope="calendar tasks")

    monkeypatch.setattr(google_auth.google_api, "exchange_code", fake_exchange_code)

    telegram_id = await google_auth.handle_callback(session, code="code-1", state=state)
    assert telegram_id == user.telegram_id

    account = await google_accounts.get_by_user_id(session, user.id)
    assert account is not None
    assert account.refresh_token != "refresh-secret"
    assert security.decrypt(account.refresh_token) == "refresh-secret"
    assert await google_auth.is_connected(session, user) is True


async def test_handle_callback_rejects_bad_state(session: AsyncSession):
    assert await google_auth.handle_callback(session, code="code-1", state="garbage") is None


async def test_get_access_token_refreshes_using_stored_refresh_token(session: AsyncSession, monkeypatch):
    user = await users.create(session, 5)
    await google_accounts.upsert(
        session, user.id, refresh_token=security.encrypt("stored-refresh"), scopes="calendar"
    )

    seen = {}

    async def fake_refresh_access_token(*, client_id, client_secret, refresh_token):
        seen["refresh_token"] = refresh_token
        return "fresh-access-token"

    monkeypatch.setattr(google_auth.google_api, "refresh_access_token", fake_refresh_access_token)

    token = await google_auth.get_access_token(session, user)
    assert token == "fresh-access-token"
    assert seen["refresh_token"] == "stored-refresh"


async def test_get_access_token_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 6)
    assert await google_auth.get_access_token(session, user) is None


async def test_disconnect_removes_account(session: AsyncSession, monkeypatch):
    user = await users.create(session, 7)
    await google_accounts.upsert(session, user.id, refresh_token=security.encrypt("tok"), scopes="calendar")

    async def fake_revoke(token):
        return None

    monkeypatch.setattr(google_auth.google_api, "revoke_token", fake_revoke)

    await google_auth.disconnect(session, user)
    assert await google_auth.is_connected(session, user) is False
