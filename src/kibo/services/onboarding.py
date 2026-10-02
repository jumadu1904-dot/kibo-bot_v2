"""Business logic behind the onboarding wizard and the equivalent edits from
Configuració/Settings (same fields, different entry point — see
docs/ARCHITECTURE.md, which only lists a single `services/onboarding`
module for both)."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from kibo.clients import open_meteo
from kibo.db.models import User
from kibo.db.repositories import users

STEPS = ["language", "location", "briefing_time", "news_topics", "google", "done"]

BRIEFING_PRESETS = ["07:00", "08:00", "09:00"]

NEWS_TOPICS = ["general", "tech", "business", "science", "health", "sports"]

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def parse_time(text: str) -> str | None:
    """Validate a user-typed "HH:MM" (24h). Returns the normalized string,
    or None if it doesn't match."""
    text = text.strip()
    return text if _TIME_RE.match(text) else None


async def apply_language(session: AsyncSession, user: User, lang: str) -> User:
    return await users.set_language(session, user, lang)


async def apply_location_city(session: AsyncSession, user: User, match: open_meteo.CityMatch) -> User:
    return await users.set_location(
        session, user, city=match.name, lat=match.lat, lon=match.lon, timezone=match.timezone
    )


async def apply_location_coords(session: AsyncSession, user: User, lat: float, lon: float) -> User:
    timezone = await open_meteo.timezone_for(lat, lon)
    return await users.set_location(session, user, city=None, lat=lat, lon=lon, timezone=timezone)


async def apply_briefing(session: AsyncSession, user: User, briefing_time: str | None) -> User:
    return await users.set_briefing(session, user, briefing_time)


async def apply_news_topics(session: AsyncSession, user: User, topics: list[str]) -> User:
    return await users.set_news_topics(session, user, topics)


async def advance_step(session: AsyncSession, user: User, step: str) -> User:
    return await users.set_onboarding_step(session, user, step)
