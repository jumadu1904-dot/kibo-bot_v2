"""Work triggered by the external cron (GET /check-reminders), not by PTB's
JobQueue: Render's free tier suspends the process after ~15 minutes without
HTTP traffic, so any in-process timer would simply never fire. cron-job.org
hits our endpoint every 5 minutes instead — often enough to also keep the
service from sleeping.

This runs as a background asyncio task so the HTTP request that triggered it
can be acknowledged immediately (see kibo.web.routes.check_reminders).
"""

import logging

from telegram.ext import Application

logger = logging.getLogger(__name__)


async def run_due_checks(bot: Application) -> None:
    """Send every reminder and daily briefing that is due right now.

    TODO(F3): query Reminder rows with status="pending" and due_at <= now,
    send them via bot.bot.send_message, mark them "sent".
    TODO(F4): query users whose local briefing_time matches the current
    UTC-converted minute and hasn't been sent today, build and send it.
    """
    logger.info("check-reminders: due-reminder and briefing checks are not implemented yet")
