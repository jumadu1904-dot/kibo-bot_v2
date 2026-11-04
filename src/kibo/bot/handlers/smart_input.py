"""Free text and voice notes outside the menu (see docs/ARCHITECTURE.md
"Entrada intel·ligent"): kibo.services.interpreter turns them into typed
actions, we show a confirmation card, and on Confirm each action is
written to Google (if connected) or stored locally.

A "task" action never gets written to Google blind: if the user named a
list and it matches one of theirs, or they only have one list, it's
resolved automatically; otherwise (several lists, none named, or a name
that doesn't match any of them) we ask which list before showing the
confirmation card at all — see `_resolve_task_lists`. An "event" action
goes through the same kind of clarification for which calendar it belongs
to (`_resolve_event_calendars`) and, if the user gave no date/time at all,
for when it is (`_first_missing_datetime` + `_show_datetime_prompt`) —
`_advance` runs all three checks, in that order, every time something
about the pending actions changes, until nothing is left to ask and the
confirmation card can finally show."""

from zoneinfo import ZoneInfo

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.calendar_choice import calendar_choice_keyboard
from kibo.bot.keyboards.confirm import cancel_only_keyboard, confirm_keyboard
from kibo.bot.keyboards.menu import back_home_keyboard
from kibo.bot.keyboards.tasklist import tasklist_choice_keyboard
from kibo.clients import gemini
from kibo.config import get_settings
from kibo.db.models import User
from kibo.db.repositories import local_tasks as local_tasks_repo
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import calendar, google_auth, interpreter, pending_actions
from kibo.services import reminders as reminders_service
from kibo.services import tasks as tasks_service
from kibo.services.interpreter import (
    Action,
    CreateEvent,
    CreateNote,
    CreateReminder,
    CreateTask,
    InterpretError,
    Query,
)


def _format_action(action: Action, lang: str, tz: ZoneInfo) -> str | None:
    if isinstance(action, CreateEvent):
        when = t("smart_input.when_all_day", lang, date=action.start.astimezone(tz).strftime("%d/%m")) \
            if action.all_day else action.start.astimezone(tz).strftime("%d/%m %H:%M")
        line = t("smart_input.action_event", lang, title=action.title, when=when)
        if action.calendar_name:
            line += " " + t("smart_input.calendar_suffix", lang, calendar=action.calendar_name)
        return line
    if isinstance(action, CreateReminder):
        when = action.due_at.astimezone(tz).strftime("%d/%m %H:%M")
        return t("smart_input.action_reminder", lang, text=action.text, when=when)
    if isinstance(action, CreateTask):
        line = t("smart_input.action_task", lang, title=action.title)
        if action.list_name:
            line += " " + t("smart_input.list_suffix", lang, list=action.list_name)
        if action.due_at:
            line += " " + t("smart_input.due_suffix", lang, date=action.due_at.astimezone(tz).strftime("%d/%m"))
        return line
    if isinstance(action, CreateNote):
        return t("smart_input.action_note", lang, text=action.text)
    return None


async def _resolve_task_lists(session, user: User, actions: list[Action]) -> int | None:
    """Fill in `tasklist_id`/`list_name` on every CreateTask that can be
    resolved without asking. Returns the index of the first action that's
    still ambiguous and needs the user to pick a list, or None if nothing
    needs asking (including: Google isn't connected, so tasks will fall
    back to a local list at execution time instead)."""
    if not await google_auth.is_connected(session, user):
        return None
    lists = await tasks_service.list_task_lists(session, user)
    if not lists:
        return None

    for index, action in enumerate(actions):
        if not isinstance(action, CreateTask) or action.tasklist_id:
            continue
        if action.list_name:
            match = await tasks_service.find_list_by_name(session, user, action.list_name)
            if match is None:
                return index
            action.tasklist_id, action.list_name = match.id, match.title
            continue
        if len(lists) == 1:
            action.tasklist_id, action.list_name = lists[0].id, lists[0].title
            continue
        return index
    return None


def _find_calendar(calendars: list[calendar.CalendarView], name: str) -> calendar.CalendarView | None:
    """Same matching rule as kibo.services.tasks.find_list_by_name: exact
    (case-insensitive) match first, then "name is contained in the title"."""
    needle = name.strip().lower()
    for item in calendars:
        if item.summary.strip().lower() == needle:
            return item
    for item in calendars:
        if needle in item.summary.strip().lower():
            return item
    return None


async def _resolve_event_calendars(session, user: User, actions: list[Action]) -> int | None:
    """Fill in `calendar_id`/`calendar_name` on every CreateEvent that can
    be resolved without asking. Returns the index of the first event that's
    still ambiguous, or None if nothing needs asking (including: Google
    isn't connected, so events fall back to a local reminder only)."""
    if not await google_auth.is_connected(session, user):
        return None
    calendars = await calendar.list_calendars(session, user)
    if not calendars:
        return None

    for index, action in enumerate(actions):
        if not isinstance(action, CreateEvent) or action.calendar_id:
            continue
        if action.calendar_name:
            match = _find_calendar(calendars, action.calendar_name)
            if match is None:
                return index
            action.calendar_id, action.calendar_name = match.id, match.summary
            continue
        if len(calendars) == 1:
            action.calendar_id, action.calendar_name = calendars[0].id, calendars[0].summary
            continue
        return index
    return None


def _first_missing_datetime(actions: list[Action]) -> int | None:
    for index, action in enumerate(actions):
        if isinstance(action, CreateEvent) and action.start is None:
            return index
    return None


async def _advance(reply, context: ContextTypes.DEFAULT_TYPE, user: User, pending_id: int, actions: list[Action]) -> None:
    """Re-checks every kind of ambiguity (in order: which task list, which
    calendar, missing date/time) and shows whichever prompt the first
    remaining one needs — or the final confirmation card once there's
    nothing left to ask. Called after every step of every clarification, so
    a message with several actions gets asked about each one in turn."""
    async with get_sessionmaker()() as session:
        tasklist_index = await _resolve_task_lists(session, user, actions)
        calendar_index = await _resolve_event_calendars(session, user, actions) if tasklist_index is None else None
        await pending_actions.save(session, pending_id, actions)

    if tasklist_index is not None:
        await _show_list_choice(reply, user, pending_id, tasklist_index, actions[tasklist_index])
        return
    if calendar_index is not None:
        await _show_calendar_choice(reply, user, pending_id, calendar_index, actions[calendar_index])
        return

    datetime_index = _first_missing_datetime(actions)
    if datetime_index is not None:
        await _show_datetime_prompt(reply, context, user, pending_id, datetime_index, actions[datetime_index])
        return

    await _show_confirm_card(reply, user, pending_id, actions)


async def _show_confirm_card(reply, user: User, pending_id: int, actions: list[Action]) -> None:
    tz = ZoneInfo(user.timezone)
    lines = [_format_action(a, user.lang, tz) for a in actions]
    text = t("smart_input.card_title", user.lang) + "\n\n" + "\n".join(lines)
    await reply(text, reply_markup=confirm_keyboard(user.lang, pending_id))


async def _show_list_choice(reply, user: User, pending_id: int, task_index: int, action: CreateTask) -> None:
    async with get_sessionmaker()() as session:
        lists = await tasks_service.list_task_lists(session, user)
    text = t("smart_input.pick_list_prompt", user.lang, title=action.title)
    markup = tasklist_choice_keyboard(user.lang, pending_id, task_index, lists or [])
    await reply(text, reply_markup=markup)


async def _show_calendar_choice(reply, user: User, pending_id: int, event_index: int, action: CreateEvent) -> None:
    async with get_sessionmaker()() as session:
        calendars = await calendar.list_calendars(session, user)
    text = t("smart_input.pick_calendar_prompt", user.lang, title=action.title)
    markup = calendar_choice_keyboard(user.lang, pending_id, event_index, calendars or [])
    await reply(text, reply_markup=markup)


async def _show_datetime_prompt(
    reply, context: ContextTypes.DEFAULT_TYPE, user: User, pending_id: int, event_index: int, action: CreateEvent
) -> None:
    context.user_data["waiting_for"] = "event_datetime"
    context.user_data["event_datetime_pending"] = (pending_id, event_index)
    text = t("smart_input.ask_datetime_prompt", user.lang, title=action.title)
    markup: InlineKeyboardMarkup = cancel_only_keyboard(user.lang, pending_id)
    await reply(text, reply_markup=markup)


async def _execute(session, user: User, action: Action) -> None:
    if isinstance(action, CreateEvent):
        google_event_id = await calendar.create_event(
            session,
            user,
            title=action.title,
            start=action.start,
            end=action.end,
            all_day=action.all_day,
            calendar_id=action.calendar_id or "primary",
        )
        await reminders_service.create(session, user, text=action.title, due_at=action.start, google_event_id=google_event_id)
    elif isinstance(action, CreateReminder):
        await reminders_service.create(session, user, text=action.text, due_at=action.due_at)
    elif isinstance(action, CreateTask):
        kwargs = {"due_at": action.due_at}
        if action.tasklist_id:
            kwargs["tasklist_id"] = action.tasklist_id
        task = await tasks_service.add_task(session, user, action.title, **kwargs)
        if task is None:
            await local_tasks_repo.create(session, user.id, kind="task", title=action.title)
    elif isinstance(action, CreateNote):
        await local_tasks_repo.create(session, user.id, kind="note", title=action.text)


async def _answer_query(user: User, question: str) -> str:
    """Answer a question about the user's own agenda/tasks/reminders using
    real data, not Gemini's imagination — asked to answer directly with no
    data, it previously fabricated plausible-sounding but made-up events
    and tasks (and once even claimed the bot had no Google Tasks access at
    all, which is simply false). This fetches what's real, then asks
    Gemini to phrase an answer grounded in that."""
    tz = ZoneInfo(user.timezone)
    async with get_sessionmaker()() as session:
        connected = await google_auth.is_connected(session, user)
        today_events = await calendar.get_today_events(session, user) if connected else None
        week_events = await calendar.get_week_events(session, user) if connected else None
        all_tasks = await tasks_service.list_all_tasks(session, user) if connected else None
        upcoming_reminders = await reminders_service.list_upcoming(session, user)

    lines = []
    if not connected:
        lines.append("Google Calendar/Tasks: not connected, no data available from them.")
    else:
        def _fmt_event(e):
            when = "all day" if e.all_day else e.start.astimezone(tz).strftime("%a %d/%m %H:%M")
            return f"{when} {e.summary}"

        lines.append("Today's calendar events: " + ("; ".join(_fmt_event(e) for e in today_events) or "none"))
        lines.append("This week's calendar events: " + ("; ".join(_fmt_event(e) for e in week_events) or "none"))
        for list_name, tasks in all_tasks:
            lines.append(f"Pending tasks in list '{list_name}': " + (", ".join(t_.title for t_ in tasks) or "none"))

    reminder_lines = [f"{r.due_at.astimezone(tz):%d/%m %H:%M} {r.text}" for r in upcoming_reminders]
    lines.append("Upcoming reminders (bot-managed, separate from calendar/tasks): " + ("; ".join(reminder_lines) or "none"))

    prompt = (
        f"Answer the user's question below in {user.lang}, briefly and naturally, as Kibo (their "
        "Telegram productivity assistant). Use ONLY the real data listed below — never invent an "
        "event, task or reminder that isn't in it. If the question asks you to change, move or delete "
        "something, you currently can't do that yet; say so honestly instead of pretending you did, "
        "but you may still point out what you found that matches, using the real data.\n\n"
        f"Real data:\n{chr(10).join(lines)}\n\n"
        f'Question: "{question}"'
    )

    settings = get_settings()
    try:
        return await gemini.answer_text(api_key=settings.gemini_api_key, model=settings.gemini_model, prompt=prompt)
    except gemini.GeminiError:
        return t("smart_input.query_error", user.lang)


async def _handle_actions(message, context: ContextTypes.DEFAULT_TYPE, user: User, actions: list[Action]) -> None:
    queries = [a for a in actions if isinstance(a, Query)]
    creatable = [a for a in actions if not isinstance(a, Query)]

    for query in queries:
        answer = await _answer_query(user, query.question)
        await message.reply_text(answer)

    if not creatable:
        if not queries:
            await message.reply_text(t("smart_input.error", user.lang))
        return

    async with get_sessionmaker()() as session:
        pending = await pending_actions.create(session, user, creatable)

    await _advance(message.reply_text, context, user, pending.id, creatable)


async def start_manual_event(message, context: ContextTypes.DEFAULT_TYPE, user: User, title: str) -> None:
    """Entry point for the Agenda menu's "new event" button (see
    kibo.bot.handlers.agenda): a manually-typed title goes through the same
    calendar/datetime clarification pipeline as an AI-detected "event"
    action, ending in the same confirmation card."""
    action = CreateEvent(type="event", title=title)
    async with get_sessionmaker()() as session:
        pending = await pending_actions.create(session, user, [action])
    await _advance(message.reply_text, context, user, pending.id, [action])


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    if user is None:
        return

    try:
        actions = await interpreter.parse(user=user, text=update.message.text)
    except InterpretError:
        await update.message.reply_text(t("smart_input.error", user.lang))
        return
    await _handle_actions(update.effective_message, context, user, actions)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    if user is None:
        return

    file = await update.message.voice.get_file()
    audio_bytes = bytes(await file.download_as_bytearray())

    try:
        actions = await interpreter.parse(user=user, audio_bytes=audio_bytes, audio_mime="audio/ogg")
    except InterpretError:
        await update.message.reply_text(t("smart_input.error", user.lang))
        return
    await _handle_actions(update.effective_message, context, user, actions)


async def on_tasklist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, arg = callbacks.parse(query.data)
    if action != "pick":
        return
    pending_id_s, task_index_s, list_index_s = arg.split(":")
    pending_id, task_index, list_index = int(pending_id_s), int(task_index_s), int(list_index_s)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        lists = await tasks_service.list_task_lists(session, user)
        if lists is None or list_index >= len(lists):
            await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
            return
        chosen = lists[list_index]

        actions = await pending_actions.set_task_list(
            session, pending_id, task_index, tasklist_id=chosen.id, list_name=chosen.title
        )
        if actions is None:
            await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
            return

    await _advance(query.edit_message_text, context, user, pending_id, actions)


async def on_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, arg = callbacks.parse(query.data)
    if action != "pick":
        return
    pending_id_s, event_index_s, calendar_index_s = arg.split(":")
    pending_id, event_index, calendar_index = int(pending_id_s), int(event_index_s), int(calendar_index_s)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        calendars = await calendar.list_calendars(session, user)
        if calendars is None or calendar_index >= len(calendars):
            await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
            return
        chosen = calendars[calendar_index]

        actions = await pending_actions.set_event_calendar(
            session, pending_id, event_index, calendar_id=chosen.id, calendar_name=chosen.summary
        )
        if actions is None:
            await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
            return

    await _advance(query.edit_message_text, context, user, pending_id, actions)


async def on_datetime_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.user_data.pop("event_datetime_pending", None)
    context.user_data.pop("waiting_for", None)
    if pending is None:
        return
    pending_id, event_index = pending

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)

    parsed = await interpreter.parse_datetime(user=user, text=update.message.text)
    if parsed is None:
        context.user_data["waiting_for"] = "event_datetime"
        context.user_data["event_datetime_pending"] = (pending_id, event_index)
        await update.message.reply_text(t("smart_input.datetime_error", user.lang))
        return
    start, all_day = parsed

    async with get_sessionmaker()() as session:
        actions = await pending_actions.set_event_datetime(session, pending_id, event_index, start=start, all_day=all_day)
    if actions is None:
        await update.message.reply_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
        return

    await _advance(update.message.reply_text, context, user, pending_id, actions)


async def on_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, arg = callbacks.parse(query.data)
    pending_id = int(arg)

    # A "no" tapped from the mid-clarification datetime prompt (see
    # _show_datetime_prompt) leaves this behind — clear it so the next
    # ordinary text message isn't mistaken for a date/time reply.
    if context.user_data.get("event_datetime_pending", (None,))[0] == pending_id:
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("event_datetime_pending", None)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)

        if action == "no":
            await pending_actions.discard(session, pending_id)
            await query.edit_message_text(t("smart_input.cancelled", user.lang), reply_markup=back_home_keyboard(user.lang))
            return

        if action == "edit":
            await pending_actions.discard(session, pending_id)
            await query.edit_message_text(t("smart_input.edit_prompt", user.lang))
            return

        actions = await pending_actions.get_actions(session, pending_id)
        if actions is None:
            await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
            return

        tz = ZoneInfo(user.timezone)
        lines = [_format_action(a, user.lang, tz) for a in actions]
        for a in actions:
            await _execute(session, user, a)
        await pending_actions.discard(session, pending_id)

    text = t("smart_input.done_header", user.lang) + "\n\n" + "\n".join(lines)
    await query.edit_message_text(text, reply_markup=back_home_keyboard(user.lang))
