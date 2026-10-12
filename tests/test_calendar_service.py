import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import users
from kibo.services import calendar


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_get_today_events_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 1)
    assert await calendar.get_today_events(session, user) is None


async def test_get_today_events_parses_timed_and_all_day(session: AsyncSession, monkeypatch):
    user = await users.create(session, 2)
    user.timezone = "Europe/Madrid"

    async def fake_get_access_token(session, user):
        return "access-token"

    async def fake_list_events(access_token, *, time_min, time_max):
        return [
            {"summary": "Meeting with Laura", "start": {"dateTime": "2026-01-01T10:00:00+01:00"}},
            {"summary": "Conference", "start": {"date": "2026-01-01"}},
        ]

    monkeypatch.setattr(calendar.google_auth, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(calendar.google_api, "list_events", fake_list_events)

    events = await calendar.get_today_events(session, user)
    assert len(events) == 2
    assert events[0].summary == "Meeting with Laura"
    assert events[0].all_day is False
    assert events[1].summary == "Conference"
    assert events[1].all_day is True


async def test_get_week_events_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 3)
    assert await calendar.get_week_events(session, user) is None
