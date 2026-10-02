from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t("menu.agenda", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "agenda"))],
        [InlineKeyboardButton(t("menu.reminders", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "reminders"))],
        [InlineKeyboardButton(t("menu.tasks", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "tasks"))],
        [InlineKeyboardButton(t("menu.briefing", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "briefing"))],
        [InlineKeyboardButton(t("menu.settings", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "settings"))],
    ]
    return InlineKeyboardMarkup(rows)


def back_home_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
                InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            ]
        ]
    )
