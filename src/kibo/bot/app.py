from telegram.ext import Application, CommandHandler

from kibo.bot.handlers import start
from kibo.config import Settings


def build_application(settings: Settings) -> Application:
    builder = Application.builder().token(settings.telegram_token)
    # Handlers await slow external APIs (Gemini, Google, weather, news), so
    # updates must be processed concurrently or one slow user would block
    # everyone else's messages behind them in the queue.
    builder = builder.concurrent_updates(True)
    if settings.bot_mode == "webhook":
        builder = builder.updater(None)  # updates arrive through FastAPI, not PTB's own polling
    application = builder.build()
    application.add_handler(CommandHandler("start", start.start))
    return application
