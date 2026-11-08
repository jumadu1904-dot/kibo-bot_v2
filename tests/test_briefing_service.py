from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import local_tasks as local_tasks_repo
from kibo.db.repositories import users
from kibo.services import briefing
from kibo.services.calendar import EventView
from kibo.services.tasks import TaskView


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def _make_user(session, telegram_id: int, **overrides):
    user = await users.create(session, telegram_id)
    user.timezone = "Europe/Madrid"
    user.lat, user.lon = 41.38, 2.18
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


class _UserStub:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeBotApi:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id, text):
        self.sent.append((chat_id, text))


class _FakeApplication:
    def __init__(self):
        self.bot = _FakeBotApi()


async def test_build_includes_every_enabled_block_when_connected(session: AsyncSession, monkeypatch):
    user = await _make_user(session, 1, news_topics=["tech"])

    async def fake_is_connected(session, user):
        return True

    async def fake_today_events(session, user):
        start = datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo(user.timezone))
        return [EventView(id="e1", calendar_id="primary", calendar_summary="", summary="Meeting", start=start, all_day=False)]

    async def fake_list_tasks(session, user):
        return [TaskView(id="1", title="Buy milk")]

    async def fake_weather_summary(lat, lon):
        return "☀️ 18°C"

    async def fake_headlines(topics, lang):
        return ["Some headline"]

    monkeypatch.setattr(briefing.google_auth, "is_connected", fake_is_connected)
    monkeypatch.setattr(briefing.calendar, "get_today_events", fake_today_events)
    monkeypatch.setattr(briefing.tasks_service, "list_tasks_all_lists", fake_list_tasks)
    monkeypatch.setattr(briefing.weather, "summary", fake_weather_summary)
    monkeypatch.setattr(briefing.news, "headlines_for_topics", fake_headlines)

    text = await briefing.build(session, user)
    assert "☀️ 18°C" in text
    assert "Meeting" in text
    assert "Buy milk" in text
    assert "Some headline" in text


async def test_build_falls_back_to_local_tasks_and_not_connected_message(session: AsyncSession, monkeypatch):
    user = await _make_user(session, 2)
    await local_tasks_repo.create(session, user.id, kind="task", title="Water the plants")

    async def fake_is_connected(session, user):
        return False

    async def fake_weather_summary(lat, lon):
        return None

    monkeypatch.setattr(briefing.google_auth, "is_connected", fake_is_connected)
    monkeypatch.setattr(briefing.weather, "summary", fake_weather_summary)

    text = await briefing.build(session, user)
    assert "Water the plants" in text
    assert "Connect Google" in text  # briefing.agenda_not_connected
    assert "No news topics selected" in text  # briefing.news_empty


async def test_build_returns_empty_message_when_no_blocks_enabled(session: AsyncSession):
    user = await _make_user(session, 3, briefing_blocks=[])
    assert await briefing.build(session, user) == "Nothing to show — enable a block in Settings."


def test_is_due_false_before_briefing_time():
    user = _UserStub(briefing_time="09:00", timezone="Europe/Madrid", last_briefing_sent=None)
    now = datetime(2026, 1, 1, 7, 0, tzinfo=timezone.utc)  # 08:00 Madrid
    assert briefing.is_due(user, now) is False


def test_is_due_true_once_local_time_passes_briefing_time():
    user = _UserStub(briefing_time="09:00", timezone="Europe/Madrid", last_briefing_sent=None)
    now = datetime(2026, 1, 1, 8, 1, tzinfo=timezone.utc)  # 09:01 Madrid
    assert briefing.is_due(user, now) is True


def test_is_due_false_when_already_sent_today():
    now = datetime(2026, 1, 1, 8, 1, tzinfo=timezone.utc)  # 09:01 Madrid, 2026-01-01 local
    user = _UserStub(briefing_time="09:00", timezone="Europe/Madrid", last_briefing_sent=date(2026, 1, 1))
    assert briefing.is_due(user, now) is False


def test_is_due_false_when_briefing_disabled():
    user = _UserStub(briefing_time=None, timezone="Europe/Madrid", last_briefing_sent=None)
    assert briefing.is_due(user, datetime.now(timezone.utc)) is False


async def test_send_due_sends_only_to_due_users_and_marks_sent(session: AsyncSession, monkeypatch):
    due_user = await _make_user(session, 10, briefing_time="09:00", briefing_blocks=[])
    not_due_user = await _make_user(session, 11, briefing_time="23:59", briefing_blocks=[])
    await _make_user(session, 12, briefing_time=None, briefing_blocks=[])  # briefing disabled

    now = datetime(2026, 1, 1, 8, 1, tzinfo=timezone.utc)  # 09:01 Madrid

    app = _FakeApplication()
    await briefing.send_due(app, session, now)

    assert app.bot.sent == [(due_user.telegram_id, "Nothing to show — enable a block in Settings.")]

    await session.refresh(due_user)
    await session.refresh(not_due_user)
    assert due_user.last_briefing_sent == date(2026, 1, 1)
    assert not_due_user.last_briefing_sent is None
