from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import Reminder


async def create(session: AsyncSession, user_id: int, *, text: str, due_at: datetime, google_event_id: str | None = None) -> Reminder:
    reminder = Reminder(user_id=user_id, text=text, due_at=due_at, google_event_id=google_event_id)
    session.add(reminder)
    await session.commit()
    return reminder


async def get_due(session: AsyncSession, before: datetime) -> list[Reminder]:
    result = await session.scalars(
        select(Reminder).where(Reminder.status == "pending", Reminder.due_at <= before)
    )
    return list(result)


async def list_upcoming(session: AsyncSession, user_id: int) -> list[Reminder]:
    result = await session.scalars(
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.status == "pending")
        .order_by(Reminder.due_at)
    )
    return list(result)


async def get_for_user(session: AsyncSession, user_id: int, reminder_id: int) -> Reminder | None:
    return await session.scalar(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
    )


async def mark_sent(session: AsyncSession, reminder: Reminder) -> None:
    reminder.status = "sent"
    await session.commit()


async def cancel(session: AsyncSession, user_id: int, reminder_id: int) -> bool:
    reminder = await get_for_user(session, user_id, reminder_id)
    if reminder is None:
        return False
    reminder.status = "cancelled"
    await session.commit()
    return True
