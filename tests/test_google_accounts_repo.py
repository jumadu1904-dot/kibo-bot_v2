import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import google_accounts, users


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_upsert_creates_then_updates(session: AsyncSession):
    user = await users.create(session, 1)
    assert await google_accounts.get_by_user_id(session, user.id) is None

    created = await google_accounts.upsert(session, user.id, refresh_token="tok-1", scopes="calendar")
    assert created.refresh_token == "tok-1"

    updated = await google_accounts.upsert(session, user.id, refresh_token="tok-2", scopes="calendar tasks")
    assert updated.id == created.id
    assert updated.refresh_token == "tok-2"
    assert updated.scopes == "calendar tasks"


async def test_delete_for_user(session: AsyncSession):
    user = await users.create(session, 2)
    await google_accounts.upsert(session, user.id, refresh_token="tok", scopes="calendar")
    await google_accounts.delete_for_user(session, user.id)
    assert await google_accounts.get_by_user_id(session, user.id) is None
