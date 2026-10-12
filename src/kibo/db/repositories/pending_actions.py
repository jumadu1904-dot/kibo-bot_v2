from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import PendingAction


async def create(session: AsyncSession, user_id: int, *, payload: list, expires_at: datetime) -> PendingAction:
    pending = PendingAction(user_id=user_id, payload=payload, expires_at=expires_at)
    session.add(pending)
    await session.commit()
    return pending


async def get(session: AsyncSession, pending_id: int) -> PendingAction | None:
    return await session.get(PendingAction, pending_id)


async def delete(session: AsyncSession, pending: PendingAction) -> None:
    await session.delete(pending)
    await session.commit()


async def update_payload(session: AsyncSession, pending: PendingAction, payload: list) -> None:
    pending.payload = payload
    await session.commit()
