from datetime import datetime, timezone

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


def _fake_access_token(monkeypatch, token: str = "access-token") -> None:
    async def fake_get_access_token(session, user):
        return token

    monkeypatch.setattr(calendar.google_auth, "get_access_token", fake_get_access_token)


def _fake_single_calendar(monkeypatch) -> None:
    async def fake_list_calendars(access_token):
        return [{"id": "primary", "summary": "Joan", "primary": True, "selected": True, "accessRole": "owner"}]

    monkeypatch.setattr(calendar.google_api, "list_calendars", fake_list_calendars)


async def test_get_today_events_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 1)
    assert await calendar.get_today_events(session, user) is None


async def test_get_today_events_parses_timed_and_all_day(session: AsyncSession, monkeypatch):
    user = await users.create(session, 2)
    user.timezone = "Europe/Madrid"

    _fake_access_token(monkeypatch)
    _fake_single_calendar(monkeypatch)

    async def fake_list_events(access_token, *, calendar_id, time_min, time_max):
        return [
            {"id": "e1", "summary": "Meeting with Laura", "start": {"dateTime": "2026-01-01T10:00:00+01:00"}},
            {"id": "e2", "summary": "Conference", "start": {"date": "2026-01-01"}},
        ]

    monkeypatch.setattr(calendar.google_api, "list_events", fake_list_events)

    events = await calendar.get_today_events(session, user)
    assert len(events) == 2
    # sorted by start — the all-day event sits at local midnight, before the 10:00 meeting
    assert events[0].summary == "Conference"
    assert events[0].all_day is True
    assert events[1].summary == "Meeting with Laura"
    assert events[1].id == "e1"
    assert events[1].all_day is False


async def test_get_today_events_merges_every_visible_calendar(session: AsyncSession, monkeypatch):
    """A secondary calendar (e.g. a shared one) must show up too — the bug
    this fixes was reading "primary" only."""
    user = await users.create(session, 3)
    user.timezone = "UTC"

    _fake_access_token(monkeypatch)

    async def fake_list_calendars(access_token):
        return [
            {"id": "primary", "summary": "Joan", "primary": True, "selected": True, "accessRole": "owner"},
            {"id": "work@group.calendar.google.com", "summary": "Work", "selected": True, "accessRole": "writer"},
            {"id": "hidden@group.calendar.google.com", "summary": "Hidden", "selected": False, "accessRole": "writer"},
            {"id": "busy-only@group.calendar.google.com", "summary": "Busy", "selected": True, "accessRole": "freeBusyReader"},
        ]

    monkeypatch.setattr(calendar.google_api, "list_calendars", fake_list_calendars)

    seen_calendar_ids = []

    async def fake_list_events(access_token, *, calendar_id, time_min, time_max):
        seen_calendar_ids.append(calendar_id)
        if calendar_id == "primary":
            return [{"id": "e1", "summary": "Personal", "start": {"dateTime": "2026-01-01T09:00:00+00:00"}}]
        if calendar_id == "work@group.calendar.google.com":
            return [{"id": "e2", "summary": "Standup", "start": {"dateTime": "2026-01-01T08:00:00+00:00"}}]
        raise AssertionError(f"should not query {calendar_id}")

    monkeypatch.setattr(calendar.google_api, "list_events", fake_list_events)

    events = await calendar.get_today_events(session, user)
    assert sorted(seen_calendar_ids) == ["primary", "work@group.calendar.google.com"]
    # merged and sorted by start time, across both calendars
    assert [e.summary for e in events] == ["Standup", "Personal"]


async def test_get_week_events_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 4)
    assert await calendar.get_week_events(session, user) is None


async def test_list_calendars_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 5)
    assert await calendar.list_calendars(session, user) is None


async def test_list_calendars_only_writable_primary_first(session: AsyncSession, monkeypatch):
    user = await users.create(session, 6)
    _fake_access_token(monkeypatch)

    async def fake_list_calendars(access_token):
        return [
            {"id": "work@x", "summary": "Work", "primary": False, "accessRole": "writer"},
            {"id": "primary", "summary": "Joan", "primary": True, "accessRole": "owner"},
            {"id": "readonly@x", "summary": "Readonly", "primary": False, "accessRole": "reader"},
        ]

    monkeypatch.setattr(calendar.google_api, "list_calendars", fake_list_calendars)
    calendars = await calendar.list_calendars(session, user)
    assert [c.id for c in calendars] == ["primary", "work@x"]
    assert calendars[0].primary is True


async def test_create_event_targets_given_calendar(session: AsyncSession, monkeypatch):
    user = await users.create(session, 7)
    _fake_access_token(monkeypatch)

    captured = {}

    async def fake_insert_event(access_token, *, calendar_id, body):
        captured["calendar_id"] = calendar_id
        captured["body"] = body
        return {"id": "new-event"}

    monkeypatch.setattr(calendar.google_api, "insert_event", fake_insert_event)

    event_id = await calendar.create_event(
        session,
        user,
        title="Dentist",
        start=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        end=None,
        all_day=False,
        calendar_id="work@x",
    )
    assert event_id == "new-event"
    assert captured["calendar_id"] == "work@x"
    assert captured["body"]["summary"] == "Dentist"


async def test_update_event_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 8)
    assert await calendar.update_event(session, user, calendar_id="primary", event_id="e1", title="New") is False


async def test_update_event_sends_only_given_fields(session: AsyncSession, monkeypatch):
    user = await users.create(session, 9)
    _fake_access_token(monkeypatch)

    captured = {}

    async def fake_update_event(access_token, *, calendar_id, event_id, body):
        captured["calendar_id"] = calendar_id
        captured["event_id"] = event_id
        captured["body"] = body
        return {}

    monkeypatch.setattr(calendar.google_api, "update_event", fake_update_event)

    ok = await calendar.update_event(session, user, calendar_id="primary", event_id="e1", title="Renamed")
    assert ok is True
    assert captured["calendar_id"] == "primary"
    assert captured["event_id"] == "e1"
    assert captured["body"] == {"summary": "Renamed"}


async def test_delete_event_false_when_not_connected(session: AsyncSession):
    user = await users.create(session, 10)
    assert await calendar.delete_event(session, user, calendar_id="primary", event_id="e1") is False


async def test_delete_event_calls_api(session: AsyncSession, monkeypatch):
    user = await users.create(session, 11)
    _fake_access_token(monkeypatch)

    captured = {}

    async def fake_delete_event(access_token, *, calendar_id, event_id):
        captured["calendar_id"] = calendar_id
        captured["event_id"] = event_id

    monkeypatch.setattr(calendar.google_api, "delete_event", fake_delete_event)

    ok = await calendar.delete_event(session, user, calendar_id="primary", event_id="e1")
    assert ok is True
    assert captured == {"calendar_id": "primary", "event_id": "e1"}
