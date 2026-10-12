"""Work triggered by the external cron (GET /check-reminders), not by PTB's
JobQueue: Render's free tier suspends the process after ~15 minutes without
HTTP traffic, so any in-process timer would simply never fire. cron-job.org
hits our endpoint every 5 minutes instead — often enough to also keep the
service from sleeping.

This runs as a background asyncio task so the HTTP request that triggered it
can be acknowledged immediately (see kibo.web.routes.check_reminders).
"""

import logging
from datetime import datetime, timezone

from telegram.error import TelegramError
from telegram.ext import Application

from kibo.db.repositories import users as users_repo
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import reminders as reminders_service

logger = logging.getLogger(__name__)


async def run_due_checks(bot: Application) -> None:
    """Send every reminder that is due right now.

    TODO(F4): query users whose local briefing_time matches the current
    UTC-converted minute and hasn't been sent today, build and send it.
    """
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as session:
        due = await reminders_service.get_due(session, now)
        for reminder in due:
            user = await users_repo.get_by_id(session, reminder.user_id)
            if user is None:
                await reminders_service.mark_sent(session, reminder)
                continue
            try:
                await bot.bot.send_message(
                    chat_id=user.telegram_id,
                    text=t("reminders.due_notification", user.lang, text=reminder.text),
                )
            except TelegramError:
                logger.warning("Failed to send reminder %s to user %s", reminder.id, user.id, exc_info=True)
                continue
            await reminders_service.mark_sent(session, reminder)
