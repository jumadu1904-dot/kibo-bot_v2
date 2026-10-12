"""The Google connect/disconnect screen, shared between the onboarding
wizard (last step before the menu) and Configuració/Settings. Connecting
itself happens outside Telegram (the "Connect Google" button is a URL
button straight to Google's consent screen); `/oauth/google/callback`
(kibo.web.routes) is what actually stores the token and tells the user it
worked. This handler only covers "Later" (skip, onboarding only) and
"Disconnect" (Settings only)."""

from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.google import google_keyboard
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import google_auth
from kibo.services import onboarding as onboarding_service


async def show(target, *, edit: bool, lang: str, user: User, show_later: bool) -> None:
    async with get_sessionmaker()() as session:
        connected = await google_auth.is_connected(session, user)
    auth_url = None if connected else google_auth.get_authorization_url(user.telegram_id)
    text = t("google.connected_prompt" if connected else "onboarding.google.prompt", lang)
    markup = google_keyboard(lang, connected=connected, auth_url=auth_url, show_later=show_later)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def _handle_later(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        user = await onboarding_service.advance_step(session, user, "done")

    from kibo.bot.handlers import menu as menu_handler

    await menu_handler.edit(query, user)


async def _handle_disconnect(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        await google_auth.disconnect(session, user)

    from kibo.bot.handlers import settings as settings_handler

    await settings_handler.edit(query, user)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, _ = callbacks.parse(query.data)

    if action == "later":
        await _handle_later(query, context)
    elif action == "disconnect":
        await _handle_disconnect(query, context)
