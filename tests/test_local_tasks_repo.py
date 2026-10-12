import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import local_tasks, users


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_create_and_list_filters_by_kind_and_done(session: AsyncSession):
    user = await users.create(session, 1)
    task = await local_tasks.create(session, user.id, kind="task", title="Buy milk")
    await local_tasks.create(session, user.id, kind="note", title="Remember this")

    tasks = await local_tasks.list_for_user(session, user.id, kind="task")
    assert [t.title for t in tasks] == ["Buy milk"]

    await local_tasks.complete(session, user.id, task.id)
    assert await local_tasks.list_for_user(session, user.id, kind="task") == []


async def test_complete_rejects_other_users_task(session: AsyncSession):
    owner = await users.create(session, 1)
    other = await users.create(session, 2)
    task = await local_tasks.create(session, owner.id, kind="task", title="Buy milk")

    assert await local_tasks.complete(session, other.id, task.id) is False
