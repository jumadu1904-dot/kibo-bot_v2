from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from kibo.bot.handlers import menu, onboarding, settings, start
from kibo.config import Settings
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t


async def _placeholder_command(update: Update, context, key: str) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    lang = user.lang if user else "en"
    await update.effective_message.reply_text(t(key, lang))


async def today_command(update: Update, context) -> None:
    await _placeholder_command(update, context, "placeholder.today")


async def tasks_command(update: Update, context) -> None:
    await _placeholder_command(update, context, "placeholder.tasks")


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

    application.add_handler(CallbackQueryHandler(onboarding.on_callback, pattern=r"^(onboard|settings):"))
    application.add_handler(CallbackQueryHandler(menu.on_callback, pattern=r"^menu:"))
    application.add_handler(CallbackQueryHandler(settings.on_callback, pattern=r"^settingsmenu:"))

    application.add_handler(MessageHandler(filters.LOCATION, onboarding.on_location))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding.on_text))
    return application
