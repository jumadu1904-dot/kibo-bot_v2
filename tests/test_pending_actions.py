from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import pending_actions as repo
from kibo.db.repositories import users
from kibo.services import interpreter, pending_actions


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_create_and_get_actions_round_trip(session: AsyncSession):
    user = await users.create(session, 1)
    actions = [
        interpreter.CreateTask(type="task", title="Buy milk"),
        interpreter.CreateNote(type="note", text="Remember this"),
    ]

    pending = await pending_actions.create(session, user, actions)
    restored = await pending_actions.get_actions(session, pending.id)

    assert len(restored) == 2
    assert isinstance(restored[0], interpreter.CreateTask)
    assert restored[0].title == "Buy milk"
    assert isinstance(restored[1], interpreter.CreateNote)


async def test_get_actions_returns_none_when_expired(session: AsyncSession):
    user = await users.create(session, 1)
    expired = await repo.create(
        session,
        user.id,
        payload=[{"type": "note", "text": "x"}],
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    assert await pending_actions.get_actions(session, expired.id) is None


async def test_get_actions_returns_none_when_missing(session: AsyncSession):
    assert await pending_actions.get_actions(session, 999) is None


async def test_discard_deletes_the_row(session: AsyncSession):
    user = await users.create(session, 1)
    pending = await pending_actions.create(session, user, [interpreter.CreateNote(type="note", text="x")])

    await pending_actions.discard(session, pending.id)
    assert await pending_actions.get_actions(session, pending.id) is None
