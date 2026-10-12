from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t

ns = callbacks.NAMESPACE_AGENDA


def agenda_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t("agenda.today_button", lang), callback_data=callbacks.build(ns, "today"))],
            [InlineKeyboardButton(t("agenda.week_button", lang), callback_data=callbacks.build(ns, "week"))],
            [
                InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
                InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            ],
        ]
    )


def agenda_results_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t("agenda.back_button", lang), callback_data=callbacks.build(ns, "menu"))],
            [
                InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
                InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            ],
        ]
    )

