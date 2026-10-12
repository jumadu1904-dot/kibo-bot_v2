"""Stores the actions behind a confirmation card between the moment
Gemini interprets a message and the moment the user taps Confirm/Edit/
Cancel (see docs/ARCHITECTURE.md "Entrada intel·ligent"). Actions are
serialized with Pydantic's own `model_dump(mode="json")` so datetimes
round-trip as ISO 8601 strings in the `payload` JSON column, and restored
through kibo.services.interpreter's models on read."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import PendingAction, User
from kibo.db.repositories import pending_actions as repo
from kibo.services.interpreter import ACTIONS_BY_TYPE, Action

PENDING_TTL = timedelta(minutes=30)


async def create(session: AsyncSession, user: User, actions: list[Action]) -> PendingAction:
    payload = [action.model_dump(mode="json") for action in actions]
    expires_at = datetime.now(timezone.utc) + PENDING_TTL
    return await repo.create(session, user.id, payload=payload, expires_at=expires_at)


async def get_actions(session: AsyncSession, pending_id: int) -> list[Action] | None:
    """Returns the pending actions, or None if the id doesn't exist or has
    expired (expired rows are left for a future cleanup job, not deleted
    here, to keep this a pure read)."""
    pending = await repo.get(session, pending_id)
    if pending is None:
        return None
    if pending.expires_at < datetime.now(timezone.utc):
        return None
    return [ACTIONS_BY_TYPE[item["type"]].model_validate(item) for item in pending.payload]


async def discard(session: AsyncSession, pending_id: int) -> None:
    pending = await repo.get(session, pending_id)
    if pending is not None:
        await repo.delete(session, pending)


async def set_task_list(session: AsyncSession, pending_id: int, task_index: int, *, tasklist_id: str, list_name: str) -> list[Action] | None:
    """Fill in the list the user picked for payload[task_index] (a "task"
    action — see kibo.bot.handlers.smart_input's "which list" step) and
    return the updated actions, or None if the pending row is gone/expired."""
    pending = await repo.get(session, pending_id)
    if pending is None or pending.expires_at < datetime.now(timezone.utc):
        return None

    payload = list(pending.payload)
    payload[task_index] = {**payload[task_index], "tasklist_id": tasklist_id, "list_name": list_name}
    await repo.update_payload(session, pending, payload)
    return [ACTIONS_BY_TYPE[item["type"]].model_validate(item) for item in payload]


async def save(session: AsyncSession, pending_id: int, actions: list[Action]) -> None:
    """Overwrite the stored payload with `actions` as they stand now (used
    after a resolution pass mutates e.g. auto-resolved task lists)."""
    pending = await repo.get(session, pending_id)
    if pending is not None:
        await repo.update_payload(session, pending, [action.model_dump(mode="json") for action in actions])
