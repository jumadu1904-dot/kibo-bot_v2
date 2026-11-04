"""Reminders: Telegram notifications at a given UTC time, independent of
Google Calendar (see docs/ARCHITECTURE.md "Planificador" and model de
dades). `due_at` is always stored in UTC; callers convert to/from the
user's timezone at the edges (handlers, interpreter)."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import Reminder, User
from kibo.db.repositories import reminders as repo


async def create(session: AsyncSession, user: User, *, text: str, due_at: datetime, google_event_id: str | None = None) -> Reminder:
    return await repo.create(session, user.id, text=text, due_at=due_at, google_event_id=google_event_id)


async def list_upcoming(session: AsyncSession, user: User) -> list[Reminder]:
    return await repo.list_upcoming(session, user.id)


async def cancel(session: AsyncSession, user: User, reminder_id: int) -> bool:
    return await repo.cancel(session, user.id, reminder_id)


async def cancel_by_google_event_id(session: AsyncSession, user: User, google_event_id: str) -> None:
    await repo.cancel_by_google_event_id(session, user.id, google_event_id)


async def get_due(session: AsyncSession, before: datetime) -> list[Reminder]:
    return await repo.get_due(session, before)


async def mark_sent(session: AsyncSession, reminder: Reminder) -> None:
    await repo.mark_sent(session, reminder)
