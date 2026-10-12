from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import LocalTask


async def create(session: AsyncSession, user_id: int, *, kind: str, title: str) -> LocalTask:
    task = LocalTask(user_id=user_id, kind=kind, title=title)
    session.add(task)
    await session.commit()
    return task


async def list_for_user(session: AsyncSession, user_id: int, *, kind: str) -> list[LocalTask]:
    result = await session.scalars(
        select(LocalTask)
        .where(LocalTask.user_id == user_id, LocalTask.kind == kind, LocalTask.done == False)  # noqa: E712
        .order_by(LocalTask.created_at)
    )
    return list(result)


async def complete(session: AsyncSession, user_id: int, task_id: int) -> bool:
    task = await session.get(LocalTask, task_id)
    if task is None or task.user_id != user_id:
        return False
    task.done = True
    await session.commit()
    return True
