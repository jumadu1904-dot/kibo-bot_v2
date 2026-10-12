"""Keyboard for the Google connect/disconnect screen, shared between the
onboarding wizard and Configuració/Settings (see kibo.bot.handlers.google)."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t


def google_keyboard(lang: str, *, connected: bool, auth_url: str | None, show_later: bool) -> InlineKeyboardMarkup:
    rows = []
    if connected:
        rows.append(
            [
                InlineKeyboardButton(
                    t("google.disconnect_button", lang),
                    callback_data=callbacks.build(callbacks.NAMESPACE_GOOGLE, "disconnect"),
                )
            ]
        )
    else:
        rows.append([InlineKeyboardButton(t("google.connect_button", lang), url=auth_url)])
        if show_later:
            rows.append(
                [
                    InlineKeyboardButton(
                        t("google.later_button", lang),
                        callback_data=callbacks.build(callbacks.NAMESPACE_GOOGLE, "later"),
                    )
                ]
            )
    rows.append(
        [
            InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
        ]
    )
    return InlineKeyboardMarkup(rows)
