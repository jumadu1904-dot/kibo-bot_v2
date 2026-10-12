from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import users
from kibo.services import reminders


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_create_and_list_upcoming(session: AsyncSession):
    user = await users.create(session, 1)
    now = datetime.now(timezone.utc)
    await reminders.create(session, user, text="Buy milk", due_at=now + timedelta(hours=1))
    await reminders.create(session, user, text="Call dentist", due_at=now + timedelta(days=1))

    upcoming = await reminders.list_upcoming(session, user)
    assert [r.text for r in upcoming] == ["Buy milk", "Call dentist"]


async def test_get_due_only_returns_pending_before_cutoff(session: AsyncSession):
    user = await users.create(session, 1)
    now = datetime.now(timezone.utc)
    due_soon = await reminders.create(session, user, text="Due now", due_at=now - timedelta(minutes=1))
    await reminders.create(session, user, text="Not yet", due_at=now + timedelta(days=1))

    due = await reminders.get_due(session, now)
    assert [r.id for r in due] == [due_soon.id]

    await reminders.mark_sent(session, due_soon)
    assert await reminders.get_due(session, now) == []


async def test_cancel_removes_from_upcoming(session: AsyncSession):
    user = await users.create(session, 1)
    reminder = await reminders.create(session, user, text="Buy milk", due_at=datetime.now(timezone.utc))

    assert await reminders.cancel(session, user, reminder.id) is True
    assert await reminders.list_upcoming(session, user) == []


async def test_cancel_unknown_reminder_returns_false(session: AsyncSession):
    user = await users.create(session, 1)
    assert await reminders.cancel(session, user, 999) is False
