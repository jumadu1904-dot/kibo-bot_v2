from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import users


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_create_and_fetch_user(session: AsyncSession):
    assert await users.get_by_telegram_id(session, 42) is None
    created = await users.create(session, 42)
    fetched = await users.get_by_telegram_id(session, 42)
    assert fetched.id == created.id
    assert fetched.lang == "en"
    assert fetched.onboarding_step == "language"
    assert fetched.briefing_blocks == ["weather", "agenda", "tasks", "news"]
    assert fetched.last_briefing_sent is None


async def test_list_with_briefing_only_returns_users_with_a_time_set(session: AsyncSession):
    with_briefing = await users.create(session, 1)
    await users.set_briefing(session, with_briefing, "08:00")
    await users.create(session, 2)  # briefing_time stays None

    result = await users.list_with_briefing(session)
    assert [u.id for u in result] == [with_briefing.id]


async def test_mark_briefing_sent(session: AsyncSession):
    user = await users.create(session, 3)
    await users.mark_briefing_sent(session, user, date(2026, 1, 1))
    assert user.last_briefing_sent == date(2026, 1, 1)
