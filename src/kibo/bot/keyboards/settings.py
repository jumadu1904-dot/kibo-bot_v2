from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    ns = callbacks.NAMESPACE_SETTINGS_MENU
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t("settings.language_button", lang), callback_data=callbacks.build(ns, "language"))],
            [InlineKeyboardButton(t("settings.location_button", lang), callback_data=callbacks.build(ns, "location"))],
            [InlineKeyboardButton(t("settings.briefing_button", lang), callback_data=callbacks.build(ns, "briefing"))],
            [InlineKeyboardButton(t("settings.topics_button", lang), callback_data=callbacks.build(ns, "topics"))],
            [InlineKeyboardButton(t("settings.google_button", lang), callback_data=callbacks.build(ns, "google"))],
            [
                InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
                InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            ],
        ]
    )
