"""Onboarding wizard (language -> location -> briefing time -> news topics
-> Google) and the equivalent steps reused from Configuració/Settings. The
`namespace` in callback_data (see kibo.bot.callbacks) says which of the two
callers is asking, so a shared step knows whether to advance
`onboarding_step` or just return to the Settings screen."""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes

from kibo.bot import callbacks
from kibo.bot.keyboards import onboarding as kb
from kibo.clients import open_meteo
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.i18n import t
from kibo.services import onboarding as service


async def show_language(target, *, edit: bool, lang: str, namespace: str) -> None:
    text = t("onboarding.language.prompt", lang)
    markup = kb.language_keyboard(namespace)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def show_briefing(target, *, edit: bool, lang: str, namespace: str) -> None:
    text = t("onboarding.briefing.prompt", lang)
    markup = kb.briefing_keyboard(namespace, lang)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def show_topics(target, *, edit: bool, lang: str, namespace: str, selected: list[str]) -> None:
    text = t("onboarding.topics.prompt", lang)
    markup = kb.topics_keyboard(selected, namespace, lang)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


def _location_reply_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t("location.share_button", lang), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def show_location(message, *, lang: str, namespace: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["waiting_for"] = "city"
    context.user_data["namespace"] = namespace
    await message.reply_text(t("onboarding.location.prompt", lang), reply_markup=_location_reply_keyboard(lang))


async def resume(message, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    """Re-send the prompt for whatever onboarding step the user is on
    (used when /start is run again before onboarding finished)."""
    namespace = callbacks.NAMESPACE_ONBOARD
    step = user.onboarding_step
    if step == "location":
        await show_location(message, lang=user.lang, namespace=namespace, context=context)
    elif step == "briefing_time":
        await show_briefing(message, edit=False, lang=user.lang, namespace=namespace)
    elif step == "news_topics":
        await show_topics(message, edit=False, lang=user.lang, namespace=namespace, selected=user.news_topics)
    elif step == "google":
        from kibo.bot.handlers import google as google_handler

        await google_handler.show(message, edit=False, lang=user.lang, user=user, show_later=True)
    else:
        await show_language(message, edit=False, lang=user.lang, namespace=namespace)


async def _continue_after_location(message, context, user: User, namespace: str) -> None:
    context.user_data.pop("waiting_for", None)
    context.user_data.pop("namespace", None)
    if namespace == callbacks.NAMESPACE_ONBOARD:
        await show_briefing(message, edit=False, lang=user.lang, namespace=namespace)
    else:
        from kibo.bot.handlers import settings as settings_handler

        await settings_handler.send(message, user)


async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    loc = update.message.location
    namespace = context.user_data.get("namespace", callbacks.NAMESPACE_ONBOARD)
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
        user = await service.apply_location_coords(session, user, loc.latitude, loc.longitude)
        if namespace == callbacks.NAMESPACE_ONBOARD:
            user = await service.advance_step(session, user, "briefing_time")
    await update.message.reply_text(t("location.saved", user.lang), reply_markup=ReplyKeyboardRemove())
    await _continue_after_location(update.message, context, user, namespace)


async def _handle_city_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
        lang = user.lang

    match = await open_meteo.geocode_city(update.message.text)
    if match is None:
        await update.message.reply_text(t("location.city_not_found", lang))
        return

    context.user_data["pending_city"] = match
    namespace = context.user_data.get("namespace", callbacks.NAMESPACE_ONBOARD)
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("location.confirm_yes", lang), callback_data=callbacks.build(namespace, "city_confirm")
                ),
                InlineKeyboardButton(
                    t("location.confirm_retry", lang), callback_data=callbacks.build(namespace, "city_retry")
                ),
            ]
        ]
    )
    await update.message.reply_text(
        t("location.confirm", lang, name=match.name, country=match.country), reply_markup=markup
    )


async def _handle_city_confirm(query, context: ContextTypes.DEFAULT_TYPE, namespace: str) -> None:
    match = context.user_data.pop("pending_city", None)
    if match is None:
        return
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        user = await service.apply_location_city(session, user, match)
        if namespace == callbacks.NAMESPACE_ONBOARD:
            user = await service.advance_step(session, user, "briefing_time")
    await query.edit_message_text(t("location.saved", user.lang))
    await _continue_after_location(query.message, context, user, namespace)


async def _handle_city_retry(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("pending_city", None)
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
    await query.edit_message_text(t("onboarding.location.prompt", user.lang))


async def _handle_custom_time_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
        lang = user.lang

    parsed = service.parse_time(update.message.text)
    if parsed is None:
        await update.message.reply_text(t("briefing.invalid_time", lang))
        return

    namespace = context.user_data.get("namespace", callbacks.NAMESPACE_ONBOARD)
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
        user = await service.apply_briefing(session, user, parsed)
        if namespace == callbacks.NAMESPACE_ONBOARD:
            user = await service.advance_step(session, user, "news_topics")

    context.user_data.pop("waiting_for", None)
    context.user_data.pop("namespace", None)
    if namespace == callbacks.NAMESPACE_ONBOARD:
        await show_topics(update.message, edit=False, lang=user.lang, namespace=namespace, selected=user.news_topics)
    else:
        from kibo.bot.handlers import settings as settings_handler

        await settings_handler.send(update.message, user)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    waiting_for = context.user_data.get("waiting_for")
    if waiting_for == "city":
        await _handle_city_text(update, context)
    elif waiting_for == "custom_time":
        await _handle_custom_time_text(update, context)
    elif waiting_for == "task_title":
        from kibo.bot.handlers import tasks as tasks_handler

        await tasks_handler.on_text(update, context)
    elif waiting_for == "event_datetime":
        from kibo.bot.handlers import smart_input

        await smart_input.on_datetime_text(update, context)
    elif waiting_for in ("event_title", "event_edit_title", "event_edit_when"):
        from kibo.bot.handlers import agenda as agenda_handler

        await agenda_handler.on_text(update, context)
    else:
        async with get_sessionmaker()() as session:
            user = await users.get_by_telegram_id(session, update.effective_user.id)
        if user is None:
            return
        if user.onboarding_step != "done":
            await update.message.reply_text(t("text.hint_use_menu", user.lang))
            return
        from kibo.bot.handlers import smart_input

        await smart_input.on_text(update, context)


async def _handle_lang(query, context: ContextTypes.DEFAULT_TYPE, namespace: str, arg: str) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        user = await service.apply_language(session, user, arg)
        if namespace == callbacks.NAMESPACE_ONBOARD:
            user = await service.advance_step(session, user, "location")

    if namespace == callbacks.NAMESPACE_ONBOARD:
        await query.edit_message_text("✅")
        await show_location(query.message, lang=user.lang, namespace=namespace, context=context)
    else:
        from kibo.bot.handlers import settings as settings_handler

        await settings_handler.edit(query, user)


async def _handle_briefing(query, context: ContextTypes.DEFAULT_TYPE, namespace: str, arg: str) -> None:
    if arg == "custom":
        async with get_sessionmaker()() as session:
            user = await users.get_by_telegram_id(session, query.from_user.id)
        context.user_data["waiting_for"] = "custom_time"
        context.user_data["namespace"] = namespace
        await query.edit_message_text(t("briefing.custom_prompt", user.lang))
        return

    briefing_time = None if arg == "off" else arg
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        user = await service.apply_briefing(session, user, briefing_time)
        if namespace == callbacks.NAMESPACE_ONBOARD:
            user = await service.advance_step(session, user, "news_topics")

    if namespace == callbacks.NAMESPACE_ONBOARD:
        await show_topics(query, edit=True, lang=user.lang, namespace=namespace, selected=user.news_topics)
    else:
        from kibo.bot.handlers import settings as settings_handler

        await settings_handler.edit(query, user)


async def _handle_topic(query, context: ContextTypes.DEFAULT_TYPE, namespace: str, arg: str) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        topics = list(user.news_topics)
        if arg in topics:
            topics.remove(arg)
        else:
            topics.append(arg)
        user = await service.apply_news_topics(session, user, topics)
    await query.edit_message_reply_markup(reply_markup=kb.topics_keyboard(user.news_topics, namespace, user.lang))


async def _handle_topics_done(query, context: ContextTypes.DEFAULT_TYPE, namespace: str) -> None:
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, query.from_user.id)
        if namespace == callbacks.NAMESPACE_ONBOARD:
            user = await service.advance_step(session, user, "google")

    if namespace == callbacks.NAMESPACE_ONBOARD:
        from kibo.bot.handlers import google as google_handler

        await google_handler.show(query, edit=True, lang=user.lang, user=user, show_later=True)
    else:
        from kibo.bot.handlers import settings as settings_handler

        await settings_handler.edit(query, user)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    namespace, action, arg = callbacks.parse(query.data)

    if action == "lang":
        await _handle_lang(query, context, namespace, arg)
    elif action == "briefing":
        await _handle_briefing(query, context, namespace, arg)
    elif action == "topic":
        await _handle_topic(query, context, namespace, arg)
    elif action == "topics_done":
        await _handle_topics_done(query, context, namespace)
    elif action == "city_confirm":
        await _handle_city_confirm(query, context, namespace)
    elif action == "city_retry":
        await _handle_city_retry(query, context)
