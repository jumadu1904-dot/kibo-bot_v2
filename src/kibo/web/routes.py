import asyncio
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from telegram import Update

from kibo.services import reminders_cron

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    """Telegram calls this on every update. We must answer fast (Telegram
    retries/gives up if we don't), so we only enqueue the update here — the
    Application's own background loop (started in the lifespan) picks it up
    and runs the (possibly slow) handler outside this request."""
    secret = request.app.state.settings.webhook_secret
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret and not hmac.compare_digest(secret, received):
        raise HTTPException(status_code=403)
    application = request.app.state.bot
    update = Update.de_json(await request.json(), application.bot)
    await application.update_queue.put(update)
    return {"ok": True}


@router.get("/check-reminders")
async def check_reminders(request: Request, token: str = "") -> dict[str, bool | str]:
    """Called every few minutes by an external cron (e.g. cron-job.org),
    since Render's free tier suspends the process when it gets no HTTP
    traffic and an in-process scheduler would never fire while asleep.

    Responds immediately and does the actual (potentially slow — weather,
    calendar, news...) work in a background task, so the cron request itself
    never times out."""
    settings = request.app.state.settings
    if settings.cron_secret and not hmac.compare_digest(settings.cron_secret, token):
        raise HTTPException(status_code=403)

    lock: asyncio.Lock = request.app.state.reminders_lock
    if lock.locked():
        logger.info("check-reminders: previous run still in progress, skipping this tick")
        return {"ok": True, "status": "skipped_already_running"}

    async def _run_locked() -> None:
        async with lock:
            await reminders_cron.run_due_checks(request.app.state.bot)

    asyncio.create_task(_run_locked())
    return {"ok": True, "status": "queued"}
