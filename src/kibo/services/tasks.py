"""Google Tasks: list / add / complete for the Tasks menu (see
docs/ARCHITECTURE.md F2), across the user's own task lists (a student's
account typically has one per subject, not just a single "My Tasks").
Returns None when the user hasn't connected Google, so handlers can show a
"connect first" prompt instead of an API error."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from kibo.clients import google_api
from kibo.db.models import User
from kibo.services import google_auth


@dataclass
class TaskView:
    id: str
    title: str
    tasklist_id: str = "@default"


@dataclass
class TaskListView:
    id: str
    title: str


async def list_task_lists(session: AsyncSession, user: User) -> list[TaskListView] | None:
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None
    items = await google_api.list_tasklists(access_token)
    return [TaskListView(id=item["id"], title=item.get("title", "")) for item in items]


async def find_list_by_name(session: AsyncSession, user: User, name: str) -> TaskListView | None:
    """Exact match first (case-insensitive), then "name is contained in the
    list title" as a looser fallback (e.g. "mates" -> "Matemàtiques"). None
    if nothing reasonable matches — callers should ask rather than guess."""
    lists = await list_task_lists(session, user)
    if not lists:
        return None
    needle = name.strip().lower()
    for item in lists:
        if item.title.strip().lower() == needle:
            return item
    for item in lists:
        if needle in item.title.strip().lower():
            return item
    return None


async def list_tasks(session: AsyncSession, user: User) -> list[TaskView] | None:
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None
    items = await google_api.list_tasks(access_token)
    return [TaskView(id=item["id"], title=item.get("title", "(untitled)")) for item in items]


async def list_all_tasks(session: AsyncSession, user: User) -> list[tuple[str, list[TaskView]]] | None:
    """Pending tasks across every list, not just the default one — used for
    grounded query answers (see kibo.bot.handlers.smart_input._answer_query)
    where "what do I have pending" needs the full picture on an account
    with one list per subject."""
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None
    lists = await google_api.list_tasklists(access_token)
    result = []
    for lst in lists:
        items = await google_api.list_tasks(access_token, tasklist_id=lst["id"])
        tasks = [TaskView(id=i["id"], title=i.get("title", "(untitled)"), tasklist_id=lst["id"]) for i in items]
        result.append((lst.get("title", ""), tasks))
    return result


async def list_tasks_all_lists(session: AsyncSession, user: User) -> list[TaskView] | None:
    """Flattened version of `list_all_tasks`, for the Tasks menu — an
    account with one list per subject/project has most of its tasks outside
    the default "My Tasks" list, which `list_tasks` alone would miss."""
    grouped = await list_all_tasks(session, user)
    if grouped is None:
        return None
    return [task for _, tasks in grouped for task in tasks]


async def add_task(
    session: AsyncSession,
    user: User,
    title: str,
    *,
    tasklist_id: str = "@default",
    due_at: datetime | None = None,
) -> TaskView | None:
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None
    # Google Tasks' `due` only has day precision — take the date in the
    # user's own timezone, not due_at's (UTC), so a task due "tonight" at
    # 23:00 local doesn't roll over to tomorrow's date.
    due = f"{due_at.astimezone(ZoneInfo(user.timezone)).date().isoformat()}T00:00:00.000Z" if due_at else None
    item = await google_api.insert_task(access_token, title=title, tasklist_id=tasklist_id, due=due)
    return TaskView(id=item["id"], title=item.get("title", title))


async def complete_task(session: AsyncSession, user: User, task_id: str, tasklist_id: str = "@default") -> bool:
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return False
    await google_api.complete_task(access_token, task_id=task_id, tasklist_id=tasklist_id)
    return True
