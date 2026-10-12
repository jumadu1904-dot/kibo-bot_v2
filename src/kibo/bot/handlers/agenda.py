from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.agenda import agenda_menu_keyboard, agenda_results_keyboard
from kibo.bot.keyboards.menu import back_home_keyboard
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import calendar, google_auth
from kibo.services.calendar import EventView


def _format_event(event: EventView, *, with_date: bool) -> str:
    time_part = "—" if event.all_day else f"{event.start:%H:%M}"
    if with_date:
        return f"{event.start:%a %d/%m} {time_part} — {event.summary}"
    return f"{time_part} — {event.summary}"


def _format_events(events: list[EventView], *, with_date: bool, lang: str) -> str:
    if not events:
        return t("agenda.empty", lang)
    return "\n".join(_format_event(event, with_date=with_date) for event in events)


async def send(message, user: User) -> None:
    async with get_sessionmaker()() as session:
        connected = await google_auth.is_connected(session, user)
    if not connected:
        await message.reply_text(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    await message.reply_text(t("agenda.prompt", user.lang), reply_markup=agenda_menu_keyboard(user.lang))


async def edit(query, user: User) -> None:
    async with get_sessionmaker()() as session:
        connected = await google_auth.is_connected(session, user)
    if not connected:
        await query.edit_message_text(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    await query.edit_message_text(t("agenda.prompt", user.lang), reply_markup=agenda_menu_keyboard(user.lang))


async def _show_results(query, user: User, *, week: bool) -> None:
    async with get_sessionmaker()() as session:
        events = await (calendar.get_week_events(session, user) if week else calendar.get_today_events(session, user))

    if events is None:
        await query.edit_message_text(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return

    title = t("agenda.week_title", user.lang) if week else t("agenda.today_title", user.lang)
    body = _format_events(events, with_date=week, lang=user.lang)
    await query.edit_message_text(f"{title}\n\n{body}", reply_markup=agenda_results_keyboard(user.lang))


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, _ = callbacks.parse(query.data)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)

    if action == "today":
        await _show_results(query, user, week=False)
    elif action == "week":
        await _show_results(query, user, week=True)
    elif action == "menu":
        await edit(query, user)
