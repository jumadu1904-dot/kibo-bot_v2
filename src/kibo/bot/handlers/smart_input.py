"""Free text and voice notes outside the menu (see docs/ARCHITECTURE.md
"Entrada intel·ligent"): kibo.services.interpreter turns them into typed
actions, we show a confirmation card, and on Confirm each action is
written to Google (if connected) or stored locally.

A "task" action never gets written to Google blind: if the user named a
list and it matches one of theirs, or they only have one list, it's
resolved automatically; otherwise (several lists, none named, or a name
that doesn't match any of them) we ask which list before showing the
confirmation card at all — see `_resolve_task_lists`."""

from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.confirm import confirm_keyboard
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
from kibo.services.interpreter import Action, CreateEvent, CreateNote, CreateReminder, CreateTask, InterpretError, Query


def _format_action(action: Action, lang: str, tz: ZoneInfo) -> str | None:
    if isinstance(action, CreateEvent):
        when = t("smart_input.when_all_day", lang, date=action.start.astimezone(tz).strftime("%d/%m")) \
            if action.all_day else action.start.astimezone(tz).strftime("%d/%m %H:%M")
        return t("smart_input.action_event", lang, title=action.title, when=when)
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


async def _execute(session, user: User, action: Action) -> None:
    if isinstance(action, CreateEvent):
        google_event_id = await calendar.create_event(
            session, user, title=action.title, start=action.start, end=action.end, all_day=action.all_day
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


async def _handle_actions(message, user: User, actions: list[Action]) -> None:
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
        ambiguous_index = await _resolve_task_lists(session, user, creatable)
        pending = await pending_actions.create(session, user, creatable)

    if ambiguous_index is not None:
        await _show_list_choice(message.reply_text, user, pending.id, ambiguous_index, creatable[ambiguous_index])
        return
    await _show_confirm_card(message.reply_text, user, pending.id, creatable)


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
    await _handle_actions(update.effective_message, user, actions)


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
    await _handle_actions(update.effective_message, user, actions)


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

        next_ambiguous = await _resolve_task_lists(session, user, actions)
        await pending_actions.save(session, pending_id, actions)

    if next_ambiguous is not None:
        await _show_list_choice(query.edit_message_text, user, pending_id, next_ambiguous, actions[next_ambiguous])
        return
    await _show_confirm_card(query.edit_message_text, user, pending_id, actions)


async def on_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, arg = callbacks.parse(query.data)
    pending_id = int(arg)

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
