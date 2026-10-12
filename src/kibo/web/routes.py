import asyncio
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from telegram import Update

from kibo.bot.keyboards.menu import main_menu_keyboard
from kibo.db.repositories import users as users_repo
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import google_auth, reminders_cron
from kibo.services import onboarding as onboarding_service

logger = logging.getLogger(__name__)
router = APIRouter()

_OAUTH_PAGE = """<!doctype html>
<html><body style="font-family: sans-serif; text-align: center; padding-top: 4rem;">
<p>{message}</p>
</body></html>"""


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    """Telegram calls this on every update. We must answer fast (Telegram
    retries/gives up if we don't), so we only enqueue the update here — the
    Application's own background loop (started in the lifespan) picks it up
    and runs the (possibly slow) handler outside this request."""
    secret = request.app.state.settings.webhook_secret_token
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret and not hmac.compare_digest(secret, received):
        raise HTTPException(status_code=403)
    application = request.app.state.bot
    update = Update.de_json(await request.json(), application.bot)
    await application.update_queue.put(update)
    return {"ok": True}


@router.get("/oauth/google/callback")
async def google_oauth_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> HTMLResponse:
    """Google redirects here after the user accepts/declines the consent
    screen. See docs/ARCHITECTURE.md "OAuth de Google (per usuari)" — we
    verify `state`, exchange `code` for tokens, store the encrypted refresh
    token, then notify the user on Telegram since this page isn't where
    they'll see the result."""
    if error or not code or not state:
        return HTMLResponse(
            _OAUTH_PAGE.format(message="Something went wrong. Go back to Telegram and try again."),
            status_code=400,
        )

    async with get_sessionmaker()() as session:
        telegram_id = await google_auth.handle_callback(session, code=code, state=state)
        if telegram_id is None:
            return HTMLResponse(
                _OAUTH_PAGE.format(message="This link is invalid or expired. Go back to Telegram and tap Connect Google again."),
                status_code=400,
            )

        user = await users_repo.get_by_telegram_id(session, telegram_id)
        if user.onboarding_step == "google":
            user = await onboarding_service.advance_step(session, user, "done")

    application = request.app.state.bot
    await application.bot.send_message(
        chat_id=telegram_id,
        text=t("google.connected_message", user.lang),
        reply_markup=main_menu_keyboard(user.lang),
    )
    return HTMLResponse(_OAUTH_PAGE.format(message="Google connected! You can close this tab and go back to Telegram."))


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
