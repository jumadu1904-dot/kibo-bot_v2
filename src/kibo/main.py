import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from kibo.bot.app import build_application
from kibo.config import get_settings
from kibo.web.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    bot = build_application(settings)
    app.state.settings = settings
    app.state.bot = bot
    # Guards GET /check-reminders against overlapping runs: cron-job.org fires
    # every 5 min, but a full check (weather/calendar/news per user) can take
    # 1-2 min, so a slow tick must not overlap with the next one.
    app.state.reminders_lock = asyncio.Lock()

    await bot.initialize()
    await bot.start()
    if settings.bot_mode == "polling":
        await bot.updater.start_polling()
    else:
        await bot.bot.set_webhook(
            f"{settings.public_url}/telegram/webhook",
            secret_token=settings.webhook_secret or None,
        )
    try:
        yield
    finally:
        if settings.bot_mode == "polling":
            await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()


app = FastAPI(title="Kibo", lifespan=lifespan)
app.include_router(router)
