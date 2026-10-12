from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import GoogleAccount


async def get_by_user_id(session: AsyncSession, user_id: int) -> GoogleAccount | None:
    return await session.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user_id))


async def upsert(
    session: AsyncSession, user_id: int, *, refresh_token: str, scopes: str
) -> GoogleAccount:
    """`refresh_token` must already be encrypted (see kibo.security.encrypt)."""
    account = await get_by_user_id(session, user_id)
    if account is None:
        account = GoogleAccount(user_id=user_id, refresh_token=refresh_token, scopes=scopes)
        session.add(account)
    else:
        account.refresh_token = refresh_token
        account.scopes = scopes
    await session.commit()
    return account


async def delete_for_user(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(GoogleAccount).where(GoogleAccount.user_id == user_id))
    await session.commit()
