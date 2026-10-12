from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.reminders import reminders_list_keyboard
from kibo.db.models import Reminder, User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import reminders as reminders_service


def _label(reminder: Reminder, tz: ZoneInfo) -> str:
    return f"{reminder.due_at.astimezone(tz):%d/%m %H:%M} — {reminder.text}"


async def _render(user: User):
    tz = ZoneInfo(user.timezone)
    async with get_sessionmaker()() as session:
        upcoming = await reminders_service.list_upcoming(session, user)
    text = t("reminders.list_title", user.lang) if upcoming else t("reminders.empty", user.lang)
    items = [(reminder.id, _label(reminder, tz)) for reminder in upcoming]
    return text, reminders_list_keyboard(user.lang, items)


async def send(message, user: User) -> None:
    text, markup = await _render(user)
    await message.reply_text(text, reply_markup=markup)


async def edit(query, user: User) -> None:
    text, markup = await _render(user)
    await query.edit_message_text(text, reply_markup=markup)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, arg = callbacks.parse(query.data)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)

    if action == "cancel":
        async with get_sessionmaker()() as session:
            await reminders_service.cancel(session, user, int(arg))
        text, markup = await _render(user)
        await query.edit_message_text(text, reply_markup=markup)
