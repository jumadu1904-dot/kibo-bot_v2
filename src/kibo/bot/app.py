import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from kibo.bot.handlers import (
    agenda,
    briefing,
    google,
    menu,
    onboarding,
    settings,
    smart_input,
    start,
)
from kibo.bot.handlers import reminders as reminders_handler
from kibo.bot.handlers import tasks as tasks_handler
from kibo.config import Settings
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Without this, a handler that raises leaves the user staring at a
    button that just... stopped responding — the exception only ever
    reached the logs. Surfacing a short message at least tells them
    something broke instead of leaving total silence."""
    logger.exception("Unhandled error while processing update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat is not None:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="⚠️ Hi ha hagut un error. Torna-ho a provar."
            )
        except TelegramError:
            logger.warning("Failed to notify user about the error above", exc_info=True)


async def today_command(update: Update, context) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    await agenda.send(update.effective_message, user)


async def tasks_command(update: Update, context) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    await tasks_handler.send(context, update.effective_message, user)


def build_application(settings_: Settings) -> Application:
    builder = Application.builder().token(settings_.telegram_token)
    # Handlers await slow external APIs (Gemini, Google, weather, news), so
    # updates must be processed concurrently or one slow user would block
    # everyone else's messages behind them in the queue.
    builder = builder.concurrent_updates(True)
    if settings_.bot_mode == "webhook":
        builder = builder.updater(None)  # updates arrive through FastAPI, not PTB's own polling
    application = builder.build()

    application.add_handler(CommandHandler("start", start.start))
    application.add_handler(CommandHandler("menu", menu.menu_command))
    application.add_handler(CommandHandler("settings", settings.settings_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("briefing_now", briefing.briefing_now_command))

    application.add_handler(CallbackQueryHandler(onboarding.on_callback, pattern=r"^(onboard|settings):"))
    application.add_handler(CallbackQueryHandler(menu.on_callback, pattern=r"^menu:"))
    application.add_handler(CallbackQueryHandler(settings.on_callback, pattern=r"^settingsmenu:"))
    application.add_handler(CallbackQueryHandler(google.on_callback, pattern=r"^google:"))
    application.add_handler(CallbackQueryHandler(agenda.on_callback, pattern=r"^agenda:"))
    application.add_handler(CallbackQueryHandler(tasks_handler.on_callback, pattern=r"^tasks:"))
    application.add_handler(CallbackQueryHandler(reminders_handler.on_callback, pattern=r"^reminders:"))
    application.add_handler(CallbackQueryHandler(smart_input.on_confirm_callback, pattern=r"^confirm:"))
    application.add_handler(CallbackQueryHandler(smart_input.on_tasklist_callback, pattern=r"^tasklist:"))
    application.add_handler(CallbackQueryHandler(smart_input.on_calendar_callback, pattern=r"^calendar:"))

    application.add_handler(MessageHandler(filters.LOCATION, onboarding.on_location))
    application.add_handler(MessageHandler(filters.VOICE, smart_input.on_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding.on_text))
    application.add_error_handler(on_error)
    return application
