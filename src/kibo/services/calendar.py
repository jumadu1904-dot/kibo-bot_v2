"""Google Calendar reads for the Agenda menu (today / this week — see
docs/ARCHITECTURE.md F2). Returns None when the user hasn't connected
Google, so handlers can show a "connect first" prompt instead of an API
error."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from kibo.clients import google_api
from kibo.db.models import User
from kibo.services import google_auth


@dataclass
class EventView:
    summary: str
    start: datetime
    all_day: bool


def _day_bounds(user: User) -> tuple[datetime, datetime]:
    tz = ZoneInfo(user.timezone)
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _week_bounds(user: User) -> tuple[datetime, datetime]:
    start, _ = _day_bounds(user)
    return start, start + timedelta(days=7)


def _parse_event(item: dict, tz: ZoneInfo) -> EventView:
    start_info = item.get("start", {})
    if "dateTime" in start_info:
        start = datetime.fromisoformat(start_info["dateTime"]).astimezone(tz)
        all_day = False
    else:
        start = datetime.fromisoformat(start_info["date"]).replace(tzinfo=tz)
        all_day = True
    return EventView(summary=item.get("summary", "(no title)"), start=start, all_day=all_day)


async def _list_events(session: AsyncSession, user: User, bounds: tuple[datetime, datetime]) -> list[EventView] | None:
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None

    time_min, time_max = bounds
    items = await google_api.list_events(
        access_token, time_min=time_min.isoformat(), time_max=time_max.isoformat()
    )
    tz = ZoneInfo(user.timezone)
    return [_parse_event(item, tz) for item in items]


async def get_today_events(session: AsyncSession, user: User) -> list[EventView] | None:
    return await _list_events(session, user, _day_bounds(user))


async def get_week_events(session: AsyncSession, user: User) -> list[EventView] | None:
    return await _list_events(session, user, _week_bounds(user))


async def create_event(
    session: AsyncSession,
    user: User,
    *,
    title: str,
    start: datetime,
    end: datetime | None,
    all_day: bool,
) -> str | None:
    """Create a Google Calendar event (used by the AI interpreter's
    confirmation card, see kibo.bot.handlers.smart_input). Returns the new
    event's id, or None if the user hasn't connected Google."""
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None

    end = end or start + timedelta(hours=1)
    if all_day:
        body = {
            "summary": title,
            "start": {"date": start.date().isoformat()},
            "end": {"date": end.date().isoformat()},
        }
    else:
        body = {
            "summary": title,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
    item = await google_api.insert_event(access_token, body=body)
    return item["id"]
