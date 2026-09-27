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
