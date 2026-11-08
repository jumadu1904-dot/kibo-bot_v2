import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.db.models import Base
from kibo.db.repositories import users
from kibo.services import tasks


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_list_tasks_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 1)
    assert await tasks.list_tasks(session, user) is None


async def test_list_tasks_maps_items(session: AsyncSession, monkeypatch):
    user = await users.create(session, 2)

    async def fake_get_access_token(session, user):
        return "access-token"

    async def fake_list_tasks(access_token):
        return [{"id": "1", "title": "Buy milk"}, {"id": "2", "title": "Call dentist"}]

    monkeypatch.setattr(tasks.google_auth, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(tasks.google_api, "list_tasks", fake_list_tasks)

    result = await tasks.list_tasks(session, user)
    assert [t.title for t in result] == ["Buy milk", "Call dentist"]


async def test_add_task_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 3)
    assert await tasks.add_task(session, user, "New task") is None


async def test_add_task_returns_created_task(session: AsyncSession, monkeypatch):
    user = await users.create(session, 4)

    async def fake_get_access_token(session, user):
        return "access-token"

    async def fake_insert_task(access_token, *, title, tasklist_id="@default", due=None):
        return {"id": "9", "title": title}

    monkeypatch.setattr(tasks.google_auth, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(tasks.google_api, "insert_task", fake_insert_task)

    result = await tasks.add_task(session, user, "New task")
    assert result.id == "9"
    assert result.title == "New task"


async def test_add_task_sends_due_date_in_users_timezone(session: AsyncSession, monkeypatch):
    from datetime import datetime, timezone

    user = await users.create(session, 7)
    user.timezone = "Europe/Madrid"
    captured = {}

    async def fake_get_access_token(session, user):
        return "access-token"

    async def fake_insert_task(access_token, *, title, tasklist_id="@default", due=None):
        captured["due"] = due
        return {"id": "9", "title": title}

    monkeypatch.setattr(tasks.google_auth, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(tasks.google_api, "insert_task", fake_insert_task)

    # 23:00 UTC on the 3rd is already the 4th in Madrid (UTC+1/+2) —
    # the due date sent to Google must follow the user's local day.
    await tasks.add_task(session, user, "New task", due_at=datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc))
    assert captured["due"] == "2026-10-04T00:00:00.000Z"


async def test_list_task_lists_none_when_not_connected(session: AsyncSession):
    user = await users.create(session, 8)
    assert await tasks.list_task_lists(session, user) is None


async def test_list_task_lists_maps_items(session: AsyncSession, monkeypatch):
    user = await users.create(session, 9)

    async def fake_get_access_token(session, user):
        return "access-token"

    async def fake_list_tasklists(access_token):
        return [{"id": "l1", "title": "Matemàtiques"}, {"id": "l2", "title": "Música"}]

    monkeypatch.setattr(tasks.google_auth, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(tasks.google_api, "list_tasklists", fake_list_tasklists)

    result = await tasks.list_task_lists(session, user)
    assert [l.title for l in result] == ["Matemàtiques", "Música"]


async def test_find_list_by_name_exact_then_substring_match(session: AsyncSession, monkeypatch):
    user = await users.create(session, 10)

    async def fake_get_access_token(session, user):
        return "access-token"

    async def fake_list_tasklists(access_token):
        return [{"id": "l1", "title": "Matemàtiques"}, {"id": "l2", "title": "Música"}]

    monkeypatch.setattr(tasks.google_auth, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(tasks.google_api, "list_tasklists", fake_list_tasklists)

    exact = await tasks.find_list_by_name(session, user, "música")
    assert exact.id == "l2"

    substring = await tasks.find_list_by_name(session, user, "mates")
    assert substring is None  # "mates" isn't contained in "Matemàtiques" the other way around

    no_match = await tasks.find_list_by_name(session, user, "sallenet")
    assert no_match is None


async def test_complete_task_false_when_not_connected(session: AsyncSession):
    user = await users.create(session, 5)
    assert await tasks.complete_task(session, user, "1") is False


async def test_complete_task_calls_client(session: AsyncSession, monkeypatch):
    user = await users.create(session, 6)
    called = {}

    async def fake_get_access_token(session, user):
        return "access-token"

    async def fake_complete_task(access_token, *, task_id, tasklist_id):
        called["task_id"] = task_id
        called["tasklist_id"] = tasklist_id
        return {"status": "completed"}

    monkeypatch.setattr(tasks.google_auth, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(tasks.google_api, "complete_task", fake_complete_task)

    assert await tasks.complete_task(session, user, "task-1") is True
    assert called["task_id"] == "task-1"
    assert called["tasklist_id"] == "@default"
