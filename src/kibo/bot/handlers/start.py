from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.handlers import onboarding
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, tg_user.id)
        is_new = user is None
        if is_new:
            user = await users.create(session, tg_user.id)

    key = "start.welcome_new" if is_new else "start.welcome_back"
    await update.effective_message.reply_text(t(key, user.lang, name=tg_user.first_name))

    if user.onboarding_step == "done":
        from kibo.bot.handlers import menu

        await menu.send(update.effective_message, user)
    elif is_new:
        await onboarding.show_language(
            update.effective_message, edit=False, lang=user.lang, namespace=callbacks.NAMESPACE_ONBOARD
        )
    else:
        await onboarding.resume(update.effective_message, context, user)
