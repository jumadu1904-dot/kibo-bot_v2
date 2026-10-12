from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.menu import back_home_keyboard, main_menu_keyboard
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t

PLACEHOLDER_ACTIONS = {"briefing"}


async def send(message, user: User) -> None:
    await message.reply_text(t("menu.title", user.lang), reply_markup=main_menu_keyboard(user.lang))


async def edit(query, user: User) -> None:
    await query.edit_message_text(t("menu.title", user.lang), reply_markup=main_menu_keyboard(user.lang))


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    await send(update.effective_message, user)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, _ = callbacks.parse(query.data)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)

    if action == "home":
        await edit(query, user)
    elif action == "settings":
        from kibo.bot.handlers import settings

        await settings.edit(query, user)
    elif action == "agenda":
        from kibo.bot.handlers import agenda

        await agenda.edit(query, user)
    elif action == "tasks":
        from kibo.bot.handlers import tasks

        await tasks.edit(query, user)
    elif action == "reminders":
        from kibo.bot.handlers import reminders

        await reminders.edit(query, user)
    elif action in PLACEHOLDER_ACTIONS:
        await query.edit_message_text(t("menu.placeholder", user.lang), reply_markup=back_home_keyboard(user.lang))
