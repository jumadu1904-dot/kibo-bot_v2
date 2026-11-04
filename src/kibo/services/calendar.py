"""Google Calendar reads/writes for the Agenda menu (see docs/ARCHITECTURE.md
F2). Returns None when the user hasn't connected Google, so handlers can
show a "connect first" prompt instead of an API error.

Events are read across every calendar the user has visible in their own
Google Calendar UI, not just "primary" — a single-calendar read was hiding
anything filed under a secondary calendar (shared, subscribed, work...)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from kibo.clients import google_api
from kibo.db.models import User
from kibo.services import google_auth


@dataclass
class EventView:
    id: str
    calendar_id: str
    calendar_summary: str
    summary: str
    start: datetime
    all_day: bool


@dataclass
class CalendarView:
    id: str
    summary: str
    primary: bool


def _day_bounds(user: User) -> tuple[datetime, datetime]:
    tz = ZoneInfo(user.timezone)
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _week_bounds(user: User) -> tuple[datetime, datetime]:
    start, _ = _day_bounds(user)
    return start, start + timedelta(days=7)


def _parse_event(item: dict, tz: ZoneInfo, *, calendar_id: str, calendar_summary: str) -> EventView:
    start_info = item.get("start", {})
    if "dateTime" in start_info:
        start = datetime.fromisoformat(start_info["dateTime"]).astimezone(tz)
        all_day = False
    else:
        start = datetime.fromisoformat(start_info["date"]).replace(tzinfo=tz)
        all_day = True
    return EventView(
        id=item["id"],
        calendar_id=calendar_id,
        calendar_summary=calendar_summary,
        summary=item.get("summary", "(no title)"),
        start=start,
        all_day=all_day,
    )


async def list_calendars(session: AsyncSession, user: User) -> list[CalendarView] | None:
    """Every calendar the user can write events to, primary first. None
    when Google isn't connected."""
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None
    items = await google_api.list_calendars(access_token)
    calendars = [
        CalendarView(id=item["id"], summary=item.get("summary", item["id"]), primary=item.get("primary", False))
        for item in items
        if item.get("accessRole") in ("owner", "writer")
    ]
    calendars.sort(key=lambda c: not c.primary)
    return calendars


async def _visible_calendars(access_token: str) -> list[tuple[str, str]]:
    """(id, summary) for every calendar shown in the user's own Google
    Calendar UI — "selected" is Google's own flag for that, defaulting to
    False for anything the user hasn't checked on there. Read-only
    (freeBusyReader) calendars are skipped since their events can't be
    fetched, only busy/free slots."""
    items = await google_api.list_calendars(access_token)
    visible = [
        (item["id"], item.get("summary", item["id"]))
        for item in items
        if item.get("selected", False) and item.get("accessRole") != "freeBusyReader"
    ]
    return visible or [("primary", "")]


async def _list_events(session: AsyncSession, user: User, bounds: tuple[datetime, datetime]) -> list[EventView] | None:
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None

    time_min, time_max = bounds
    tz = ZoneInfo(user.timezone)
    events: list[EventView] = []
    for calendar_id, calendar_summary in await _visible_calendars(access_token):
        items = await google_api.list_events(
            access_token, calendar_id=calendar_id, time_min=time_min.isoformat(), time_max=time_max.isoformat()
        )
        events += [
            _parse_event(item, tz, calendar_id=calendar_id, calendar_summary=calendar_summary) for item in items
        ]
    events.sort(key=lambda e: e.start)
    return events


async def get_today_events(session: AsyncSession, user: User) -> list[EventView] | None:
    return await _list_events(session, user, _day_bounds(user))


async def get_week_events(session: AsyncSession, user: User) -> list[EventView] | None:
    return await _list_events(session, user, _week_bounds(user))


def _event_body(*, title: str, start: datetime, end: datetime | None, all_day: bool) -> dict:
    end = end or start + timedelta(hours=1)
    if all_day:
        return {
            "summary": title,
            "start": {"date": start.date().isoformat()},
            "end": {"date": end.date().isoformat()},
        }
    return {
        "summary": title,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }


async def create_event(
    session: AsyncSession,
    user: User,
    *,
    title: str,
    start: datetime,
    end: datetime | None,
    all_day: bool,
    calendar_id: str = "primary",
) -> str | None:
    """Create a Google Calendar event (used by the AI interpreter's
    confirmation card, see kibo.bot.handlers.smart_input, and by the Agenda
    menu's manual "new event" flow). Returns the new event's id, or None if
    the user hasn't connected Google."""
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return None

    body = _event_body(title=title, start=start, end=end, all_day=all_day)
    item = await google_api.insert_event(access_token, calendar_id=calendar_id, body=body)
    return item["id"]


async def update_event(
    session: AsyncSession,
    user: User,
    *,
    calendar_id: str,
    event_id: str,
    title: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    all_day: bool = False,
) -> bool:
    """Partial update: only the fields given are changed. Returns False if
    Google isn't connected."""
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return False

    body: dict = {}
    if title is not None:
        body["summary"] = title
    if start is not None:
        end = end or start + timedelta(hours=1)
        if all_day:
            body["start"] = {"date": start.date().isoformat()}
            body["end"] = {"date": end.date().isoformat()}
        else:
            body["start"] = {"dateTime": start.isoformat()}
            body["end"] = {"dateTime": end.isoformat()}

    await google_api.update_event(access_token, calendar_id=calendar_id, event_id=event_id, body=body)
    return True


async def delete_event(session: AsyncSession, user: User, *, calendar_id: str, event_id: str) -> bool:
    access_token = await google_auth.get_access_token(session, user)
    if access_token is None:
        return False
    await google_api.delete_event(access_token, calendar_id=calendar_id, event_id=event_id)
    return True
