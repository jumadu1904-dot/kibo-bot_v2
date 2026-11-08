from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.menu import back_home_keyboard
from kibo.bot.keyboards.tasks import tasks_list_keyboard
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import google_auth
from kibo.services import tasks as tasks_service


async def _render(context: ContextTypes.DEFAULT_TYPE, user: User):
    """Fetch the task list across every Google task list (not just the
    default one — accounts with one list per subject keep most tasks
    elsewhere) and build (text, markup), or None if Google isn't connected.
    Task refs (which list + task id a tapped button means) are kept in
    context.user_data, same pattern as kibo.bot.handlers.agenda."""
    async with get_sessionmaker()() as session:
        items = await tasks_service.list_tasks_all_lists(session, user)
    if items is None:
        return None
    context.user_data["tasks_refs"] = {
        i: {"task_id": item.id, "tasklist_id": item.tasklist_id} for i, item in enumerate(items)
    }
    text = t("tasks.list_title", user.lang) if items else t("tasks.empty", user.lang)
    return text, tasks_list_keyboard(user.lang, items)


async def send(context: ContextTypes.DEFAULT_TYPE, message, user: User) -> None:
    async with get_sessionmaker()() as session:
        connected = await google_auth.is_connected(session, user)
    if not connected:
        await message.reply_text(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    text, markup = await _render(context, user)
    await message.reply_text(text, reply_markup=markup)


async def edit(context: ContextTypes.DEFAULT_TYPE, query, user: User) -> None:
    async with get_sessionmaker()() as session:
        connected = await google_auth.is_connected(session, user)
    if not connected:
        await query.edit_message_text(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    text, markup = await _render(context, user)
    await query.edit_message_text(text, reply_markup=markup)


async def _handle_done(query, context: ContextTypes.DEFAULT_TYPE, user: User, idx: int) -> None:
    ref = (context.user_data.get("tasks_refs") or {}).get(idx)
    if ref is None:
        await query.edit_message_text(t("smart_input.expired", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    async with get_sessionmaker()() as session:
        await tasks_service.complete_task(session, user, ref["task_id"], tasklist_id=ref["tasklist_id"])
    result = await _render(context, user)
    if result is None:
        await query.edit_message_text(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return
    text, markup = result
    await query.edit_message_text(text, reply_markup=markup)


async def _handle_add(query, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    context.user_data["waiting_for"] = "task_title"
    await query.edit_message_text(t("tasks.add_prompt", user.lang))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_for", None)
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
        task = await tasks_service.add_task(session, user, update.message.text.strip())

    if task is None:
        await update.message.reply_text(t("google.not_connected", user.lang), reply_markup=back_home_keyboard(user.lang))
        return

    result = await _render(context, user)
    text, markup = result
    await update.message.reply_text(t("tasks.added", user.lang, title=task.title))
    await update.message.reply_text(text, reply_markup=markup)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, arg = callbacks.parse(query.data)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)

    if action == "done":
        await _handle_done(query, context, user, int(arg))
    elif action == "add":
        await _handle_add(query, context, user)
