import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kibo.clients.open_meteo import CityMatch
from kibo.db.models import Base
from kibo.db.repositories import users
from kibo.services import onboarding


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("08:30", "08:30"),
        ("23:59", "23:59"),
        ("00:00", "00:00"),
        (" 09:15 ", "09:15"),
        ("8:30", None),
        ("24:00", None),
        ("09:60", None),
        ("not a time", None),
    ],
)
def test_parse_time(text, expected):
    assert onboarding.parse_time(text) == expected


async def test_apply_language(session: AsyncSession):
    user = await users.create(session, 1)
    updated = await onboarding.apply_language(session, user, "ca")
    assert updated.lang == "ca"


async def test_apply_location_city(session: AsyncSession):
    user = await users.create(session, 2)
    match = CityMatch(name="Barcelona", country="Spain", lat=41.38, lon=2.18, timezone="Europe/Madrid")
    updated = await onboarding.apply_location_city(session, user, match)
    assert updated.city == "Barcelona"
    assert updated.lat == 41.38
    assert updated.timezone == "Europe/Madrid"


async def test_apply_location_coords(session: AsyncSession, monkeypatch):
    async def fake_timezone_for(lat, lon):
        return "Europe/Madrid"

    monkeypatch.setattr(onboarding.open_meteo, "timezone_for", fake_timezone_for)
    user = await users.create(session, 3)
    updated = await onboarding.apply_location_coords(session, user, 41.38, 2.18)
    assert updated.city is None
    assert updated.lat == 41.38
    assert updated.timezone == "Europe/Madrid"


async def test_apply_briefing(session: AsyncSession):
    user = await users.create(session, 4)
    updated = await onboarding.apply_briefing(session, user, "08:00")
    assert updated.briefing_time == "08:00"
    updated = await onboarding.apply_briefing(session, user, None)
    assert updated.briefing_time is None


async def test_apply_news_topics(session: AsyncSession):
    user = await users.create(session, 5)
    updated = await onboarding.apply_news_topics(session, user, ["tech", "sports"])
    assert updated.news_topics == ["tech", "sports"]


async def test_advance_step(session: AsyncSession):
    user = await users.create(session, 6)
    assert user.onboarding_step == "language"
    updated = await onboarding.advance_step(session, user, "location")
    assert updated.onboarding_step == "location"
