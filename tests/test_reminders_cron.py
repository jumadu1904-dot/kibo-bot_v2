from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import users
from kibo.services import reminders, reminders_cron


class _FakeBotApi:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id, text):
        self.sent.append((chat_id, text))


class _FakeApplication:
    def __init__(self):
        self.bot = _FakeBotApi()


@pytest.fixture
async def session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(reminders_cron, "get_sessionmaker", lambda: sessionmaker)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


async def test_run_due_checks_sends_and_marks_sent(session: AsyncSession):
    user = await users.create(session, 111)
    now = datetime.now(timezone.utc)
    due = await reminders.create(session, user, text="Buy milk", due_at=now - timedelta(minutes=1))
    future = await reminders.create(session, user, text="Not yet", due_at=now + timedelta(days=1))

    app = _FakeApplication()
    await reminders_cron.run_due_checks(app)

    assert app.bot.sent == [(111, "⏰ Reminder: Buy milk")]

    # run_due_checks committed through its own (monkeypatched) session, so
    # refresh these ORM objects — otherwise `session`'s identity map would
    # still hand back the stale pre-update attributes.
    await session.refresh(due)
    await session.refresh(future)
    assert due.status == "sent"
    assert future.status == "pending"


async def test_run_due_checks_also_sends_due_briefings(session: AsyncSession):
    user = await users.create(session, 222)
    user.timezone = "UTC"
    user.briefing_time = "00:00"
    user.briefing_blocks = []
    await session.commit()

    app = _FakeApplication()
    await reminders_cron.run_due_checks(app)

    assert app.bot.sent == [(222, "Nothing to show — enable a block in Settings.")]
    await session.refresh(user)
    assert user.last_briefing_sent is not None
