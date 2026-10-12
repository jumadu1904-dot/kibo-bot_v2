from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t

ns = callbacks.NAMESPACE_REMINDERS


def reminders_list_keyboard(lang: str, items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """`items` are (reminder_id, label) pairs — the handler formats the
    label (local time + text) since it knows the user's timezone."""
    rows = [
        [InlineKeyboardButton(label, callback_data=callbacks.build(ns, "cancel", str(reminder_id)))]
        for reminder_id, label in items
    ]
    rows.append(
        [
            InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
        ]
    )
    return InlineKeyboardMarkup(rows)
