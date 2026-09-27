from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import User


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def create(session: AsyncSession, telegram_id: int, lang: str = "en") -> User:
    user = User(telegram_id=telegram_id, lang=lang)
    session.add(user)
    await session.commit()
    return user
