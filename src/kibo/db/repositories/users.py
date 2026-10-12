from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kibo.db.models import User


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def create(session: AsyncSession, telegram_id: int, lang: str = "en") -> User:
    user = User(telegram_id=telegram_id, lang=lang)
    session.add(user)
    await session.commit()
    return user


async def set_language(session: AsyncSession, user: User, lang: str) -> User:
    user.lang = lang
    await session.commit()
    return user


async def set_location(
    session: AsyncSession,
    user: User,
    *,
    city: str | None,
    lat: float,
    lon: float,
    timezone: str,
) -> User:
    user.city = city
    user.lat = lat
    user.lon = lon
    user.timezone = timezone
    await session.commit()
    return user


async def set_briefing(session: AsyncSession, user: User, briefing_time: str | None) -> User:
    user.briefing_time = briefing_time
    await session.commit()
    return user


async def set_news_topics(session: AsyncSession, user: User, topics: list[str]) -> User:
    user.news_topics = topics
    await session.commit()
    return user


async def set_onboarding_step(session: AsyncSession, user: User, step: str) -> User:
    user.onboarding_step = step
    await session.commit()
    return user
