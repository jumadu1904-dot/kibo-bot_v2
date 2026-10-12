from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards.settings import settings_keyboard
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import google_auth

_LANGUAGE_NAMES = {"en": "English", "es": "Español", "ca": "Català"}


def _location_text(user: User, lang: str) -> str:
    if user.city:
        return user.city
    if user.lat is not None and user.lon is not None:
        return f"{user.lat:.2f}, {user.lon:.2f}"
    return t("settings.value_none", lang)


def _topics_text(user: User, lang: str) -> str:
    if not user.news_topics:
        return t("settings.value_none", lang)
    return ", ".join(t(f"topics.{topic}", lang) for topic in user.news_topics)


def summary_text(user: User, *, google_connected: bool) -> str:
    lang = user.lang
    google = t("settings.value_connected", lang) if google_connected else t("settings.value_not_connected", lang)
    return t(
        "settings.summary",
        lang,
        language=_LANGUAGE_NAMES.get(lang, lang),
        location=_location_text(user, lang),
        briefing=user.briefing_time or t("settings.value_off", lang),
        topics=_topics_text(user, lang),
        google=google,
    )


async def _is_google_connected(user: User) -> bool:
    async with get_sessionmaker()() as session:
        return await google_auth.is_connected(session, user)


async def send(message, user: User) -> None:
    connected = await _is_google_connected(user)
    await message.reply_text(summary_text(user, google_connected=connected), reply_markup=settings_keyboard(user.lang))


async def edit(query, user: User) -> None:
    connected = await _is_google_connected(user)
    await query.edit_message_text(summary_text(user, google_connected=connected), reply_markup=settings_keyboard(user.lang))


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    await send(update.effective_message, user)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, _ = callbacks.parse(query.data)

    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)

    from kibo.bot.handlers import onboarding

    namespace = callbacks.NAMESPACE_SETTINGS
    if action == "language":
        await onboarding.show_language(query, edit=True, lang=user.lang, namespace=namespace)
    elif action == "location":
        await query.edit_message_text("✅")
        await onboarding.show_location(query.message, lang=user.lang, namespace=namespace, context=context)
    elif action == "briefing":
        await onboarding.show_briefing(query, edit=True, lang=user.lang, namespace=namespace)
    elif action == "topics":
        await onboarding.show_topics(query, edit=True, lang=user.lang, namespace=namespace, selected=user.news_topics)
    elif action == "google":
        from kibo.bot.handlers import google as google_handler

        await google_handler.show(query, edit=True, lang=user.lang, user=user, show_later=False)
