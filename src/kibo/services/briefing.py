"""Daily briefing (see docs/SCOPE.md #4 and docs/ARCHITECTURE.md F4): one
message combining weather, today's agenda, pending tasks and news
headlines, built from the user's `briefing_blocks`. Sent either by the
cron at `briefing_time` (`send_due`, called from
kibo.services.reminders_cron on every /check-reminders tick) or on demand
(the ☀️ Briefing menu button, /briefing_now — see
kibo.bot.handlers.briefing), which just calls `build` directly."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from telegram.error import TelegramError
from telegram.ext import Application

from kibo.db.models import User
from kibo.db.repositories import local_tasks as local_tasks_repo
from kibo.db.repositories import users as users_repo
from kibo.i18n import t
from kibo.services import calendar, google_auth, news, weather
from kibo.services import tasks as tasks_service

logger = logging.getLogger(__name__)


async def _agenda_block(session: AsyncSession, user: User) -> str:
    if not await google_auth.is_connected(session, user):
        return t("briefing.agenda_not_connected", user.lang)
    events = await calendar.get_today_events(session, user)
    if not events:
        return t("agenda.empty", user.lang)
    tz = ZoneInfo(user.timezone)
    lines = []
    for event in events:
        time_part = "—" if event.all_day else f"{event.start.astimezone(tz):%H:%M}"
        lines.append(f"{time_part} — {event.summary}")
    return "\n".join(lines)


async def _tasks_block(session: AsyncSession, user: User) -> str:
    if await google_auth.is_connected(session, user):
        items = await tasks_service.list_tasks(session, user)
    else:
        items = await local_tasks_repo.list_for_user(session, user.id, kind="task")
    titles = [item.title for item in items] if items else []
    if not titles:
        return t("tasks.empty", user.lang)
    return "\n".join(f"• {title}" for title in titles)


async def _news_block(user: User) -> str:
    if not user.news_topics:
        return t("briefing.news_empty", user.lang)
    titles = await news.headlines_for_topics(user.news_topics, user.lang)
    if not titles:
        return t("briefing.news_empty", user.lang)
    return "\n".join(f"• {title}" for title in titles)


async def build(session: AsyncSession, user: User) -> str:
    """Compose the briefing text from the blocks the user has enabled
    (`user.briefing_blocks`)."""
    blocks = user.briefing_blocks or []
    sections = []

    if "weather" in blocks and user.lat is not None and user.lon is not None:
        weather_line = await weather.summary(user.lat, user.lon)
        if weather_line:
            sections.append(weather_line)
    if "agenda" in blocks:
        sections.append(f"{t('agenda.today_title', user.lang)}\n{await _agenda_block(session, user)}")
    if "tasks" in blocks:
        sections.append(f"{t('briefing.tasks_title', user.lang)}\n{await _tasks_block(session, user)}")
    if "news" in blocks:
        sections.append(f"{t('briefing.news_title', user.lang)}\n{await _news_block(user)}")

    if not sections:
        return t("briefing.empty", user.lang)
    return f"{t('briefing.title', user.lang)}\n\n" + "\n\n".join(sections)


def is_due(user: User, now_utc: datetime) -> bool:
    """True once local time has reached `briefing_time` and today's local
    date hasn't had one sent yet — `last_briefing_sent` is what makes this
    fire exactly once per day despite the cron ticking every 5 minutes
    (see docs/ARCHITECTURE.md "Planificador")."""
    if not user.briefing_time:
        return False
    local_now = now_utc.astimezone(ZoneInfo(user.timezone))
    if user.last_briefing_sent == local_now.date():
        return False
    return local_now.strftime("%H:%M") >= user.briefing_time


async def send_due(bot: Application, session: AsyncSession, now_utc: datetime) -> None:
    """Build and send the briefing to every user whose `briefing_time` has
    been reached today and hasn't had one sent yet."""
    for user in await users_repo.list_with_briefing(session):
        if not is_due(user, now_utc):
            continue
        text = await build(session, user)
        try:
            await bot.bot.send_message(chat_id=user.telegram_id, text=text)
        except TelegramError:
            logger.warning("Failed to send briefing to user %s", user.id, exc_info=True)
            continue
        local_date = now_utc.astimezone(ZoneInfo(user.timezone)).date()
        await users_repo.mark_briefing_sent(session, user, local_date)
