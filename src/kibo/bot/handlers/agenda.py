"""Agenda menu: read-only today/week views plus full event CRUD. Reading
merges every calendar visible in the user's own Google Calendar
(kibo.services.calendar), not just "primary". Creating an event from here
funnels through the exact same calendar/datetime clarification pipeline as
the AI's free-text flow (kibo.bot.handlers.smart_input.start_manual_event)
so both paths behave identically and still end in a confirmation card.

Editing/deleting an existing event is simpler (no Gemini involved): pick a
field, type the new value, write it straight to Google — see `on_text`'s
"event_edit_*" branches and `_apply_edit_title`/`_apply_edit_when`. Event
references (which calendar + event id a tapped button means) are kept in
context.user_data["agenda_events"], keyed by the index shown in the list —
a (calendar_id, event_id) pair is routinely too long for Telegram's 64-byte
callback_data once the calendar is a shared/email-like id."""

from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.agenda import (
    agenda_menu_keyboard,
    agenda_results_keyboard,
    delete_confirm_keyboard,
    edit_field_keyboard,
    event_detail_keyboard,
)
from kibo.bot.keyboards.menu import back_home_keyboard
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import calendar, google_auth, interpreter
from kibo.services import reminders as reminders_service
from kibo.services.calendar import EventView


def _format_event(event: EventView, *, with_date: bool, show_calendar: bool) -> str:
    time_part = "—" if event.all_day else f"{event.start:%H:%M}"
    line = f"{event.start:%a %d/%m} {time_part} — {event.summary}" if with_date else f"{time_part} — {event.summary}"
    if show_calendar and event.calendar_summary:
        line += f" ({event.calendar_summary})"
    return line


def _format_events(events: list[EventView], *, with_date: bool, lang: str) -> str:
    if not events:
        return t("agenda.empty", lang)
    # Only label events with their calendar when the day/week actually mixes
    # more than one — no need to clutter the common single-calendar case.
    show_calendar = len({e.calendar_id for e in events}) > 1
    return "\n".join(_format_event(event, with_date=with_date, show_calendar=show_calendar) for event in events)


def _button_label(event: EventView) -> str:
    time_part = "📅" if event.all_day else f"{event.start:%H:%M}"
    title = event.summary if len(event.summary) <= 28 else event.summary[:27] + "…"
    return f"{time_part} {title}"


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


async def _show_results(respond, context: ContextTypes.DEFAULT_TYPE, user: User, *, week: bool) -> None:
    async with get_sessionmaker()() as session:
        events = await (calendar.get_week_events(session, user) if week else calendar.get_today_events(session, user))

    if events is None:
        await respond(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return

    view = "week" if week else "today"
    context.user_data["agenda_view"] = view
    context.user_data["agenda_events"] = {
        i: {"calendar_id": e.calendar_id, "event_id": e.id, "summary": e.summary, "view": view}
        for i, e in enumerate(events)
    }

    title = t("agenda.week_title", user.lang) if week else t("agenda.today_title", user.lang)
    body = _format_events(events, with_date=week, lang=user.lang)
    labels = [_button_label(e) for e in events]
    await respond(f"{title}\n\n{body}", reply_markup=agenda_results_keyboard(user.lang, labels))


def _event_ref(context: ContextTypes.DEFAULT_TYPE, idx: int) -> dict | None:
    return (context.user_data.get("agenda_events") or {}).get(idx)


async def _show_event_detail(query, context: ContextTypes.DEFAULT_TYPE, user: User, idx: int) -> None:
    ref = _event_ref(context, idx)
    if ref is None:
        await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    text = t("agenda.event_detail", user.lang, title=ref["summary"])
    await query.edit_message_text(text, reply_markup=event_detail_keyboard(user.lang, idx))


async def _show_edit_menu(query, context: ContextTypes.DEFAULT_TYPE, user: User, idx: int) -> None:
    ref = _event_ref(context, idx)
    if ref is None:
        await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    await query.edit_message_text(t("agenda.edit_field_prompt", user.lang, title=ref["summary"]), reply_markup=edit_field_keyboard(user.lang, idx))


async def _start_edit_field(query, context: ContextTypes.DEFAULT_TYPE, user: User, idx: int, field: str) -> None:
    ref = _event_ref(context, idx)
    if ref is None:
        await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    context.user_data["editing_event"] = ref
    if field == "title":
        context.user_data["waiting_for"] = "event_edit_title"
        await query.edit_message_text(t("agenda.edit_title_prompt", user.lang))
    else:
        context.user_data["waiting_for"] = "event_edit_when"
        await query.edit_message_text(t("agenda.edit_when_prompt", user.lang))


async def _show_delete_confirm(query, context: ContextTypes.DEFAULT_TYPE, user: User, idx: int) -> None:
    ref = _event_ref(context, idx)
    if ref is None:
        await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    await query.edit_message_text(
        t("agenda.delete_confirm_prompt", user.lang, title=ref["summary"]), reply_markup=delete_confirm_keyboard(user.lang, idx)
    )


async def _delete_event(query, context: ContextTypes.DEFAULT_TYPE, user: User, idx: int) -> None:
    ref = _event_ref(context, idx)
    if ref is None:
        await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    async with get_sessionmaker()() as session:
        await calendar.delete_event(session, user, calendar_id=ref["calendar_id"], event_id=ref["event_id"])
        await reminders_service.cancel_by_google_event_id(session, user, ref["event_id"])
    await _show_results(query.edit_message_text, context, user, week=(ref["view"] == "week"))


async def _start_new_event(query, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    context.user_data["waiting_for"] = "event_title"
    await query.edit_message_text(t("agenda.new_event_prompt", user.lang))


async def _apply_edit_title(message, context: ContextTypes.DEFAULT_TYPE, user: User, title: str) -> None:
    ref = context.user_data.pop("editing_event", None)
    if ref is None:
        return
    async with get_sessionmaker()() as session:
        await calendar.update_event(session, user, calendar_id=ref["calendar_id"], event_id=ref["event_id"], title=title)
    await message.reply_text(t("agenda.edit_done", user.lang))
    await _show_results(message.reply_text, context, user, week=(ref["view"] == "week"))


async def _apply_edit_when(message, context: ContextTypes.DEFAULT_TYPE, user: User, text: str) -> None:
    ref = context.user_data.pop("editing_event", None)
    if ref is None:
        return
    parsed = await interpreter.parse_datetime(user=user, text=text)
    if parsed is None:
        context.user_data["editing_event"] = ref
        context.user_data["waiting_for"] = "event_edit_when"
        await message.reply_text(t("smart_input.datetime_error", user.lang))
        return
    start, all_day = parsed
    async with get_sessionmaker()() as session:
        await calendar.update_event(
            session, user, calendar_id=ref["calendar_id"], event_id=ref["event_id"], start=start, all_day=all_day
        )
    await message.reply_text(t("agenda.edit_done", user.lang))
    await _show_results(message.reply_text, context, user, week=(ref["view"] == "week"))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes a text reply for the agenda's own flows: a new event's title,
    or a direct edit of an existing event's title/when (see onboarding.on_text,
    which dispatches here by `waiting_for`)."""
    waiting_for = context.user_data.get("waiting_for")
    context.user_data.pop("waiting_for", None)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    if user is None:
        return

    text = update.message.text.strip()
    if waiting_for == "event_title":
        from kibo.bot.handlers import smart_input

        await smart_input.start_manual_event(update.effective_message, context, user, text)
    elif waiting_for == "event_edit_title":
        await _apply_edit_title(update.effective_message, context, user, text)
    elif waiting_for == "event_edit_when":
        await _apply_edit_when(update.effective_message, context, user, text)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, arg = callbacks.parse(query.data)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)

    if action == "today":
        await _show_results(query.edit_message_text, context, user, week=False)
    elif action == "week":
        await _show_results(query.edit_message_text, context, user, week=True)
    elif action == "menu":
        await edit(query, user)
    elif action == "new":
        await _start_new_event(query, context, user)
    elif action == "ev":
        await _show_event_detail(query, context, user, int(arg))
    elif action == "editmenu":
        await _show_edit_menu(query, context, user, int(arg))
    elif action == "editfield":
        idx_s, field = arg.split(":")
        await _start_edit_field(query, context, user, int(idx_s), field)
    elif action == "delconfirm":
        await _show_delete_confirm(query, context, user, int(arg))
    elif action == "delyes":
        await _delete_event(query, context, user, int(arg))
    elif action == "back":
        view = context.user_data.get("agenda_view", "today")
        await _show_results(query.edit_message_text, context, user, week=(view == "week"))
