from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t

ns = callbacks.NAMESPACE_AGENDA


def agenda_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t("agenda.today_button", lang), callback_data=callbacks.build(ns, "today"))],
            [InlineKeyboardButton(t("agenda.week_button", lang), callback_data=callbacks.build(ns, "week"))],
            [InlineKeyboardButton(t("agenda.new_event_button", lang), callback_data=callbacks.build(ns, "new"))],
            [
                InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
                InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            ],
        ]
    )


def agenda_results_keyboard(lang: str, event_labels: list[str]) -> InlineKeyboardMarkup:
    """One row per event (tap to view/edit/delete it), then the usual nav
    rows. `event_labels[i]` is shown on a button carrying index `i`, which
    the handler resolves against context.user_data["agenda_events"] (event
    ids don't fit Telegram's 64-byte callback_data alongside a calendar id)."""
    rows = [
        [InlineKeyboardButton(label, callback_data=callbacks.build(ns, "ev", str(i)))]
        for i, label in enumerate(event_labels)
    ]
    rows.append([InlineKeyboardButton(t("agenda.new_event_button", lang), callback_data=callbacks.build(ns, "new"))])
    rows.append([InlineKeyboardButton(t("agenda.back_button", lang), callback_data=callbacks.build(ns, "menu"))])
    rows.append(
        [
            InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
        ]
    )
    return InlineKeyboardMarkup(rows)


def event_detail_keyboard(lang: str, idx: int) -> InlineKeyboardMarkup:
    arg = str(idx)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("agenda.edit_button", lang), callback_data=callbacks.build(ns, "editmenu", arg)),
                InlineKeyboardButton(t("agenda.delete_button", lang), callback_data=callbacks.build(ns, "delconfirm", arg)),
            ],
            [InlineKeyboardButton(t("agenda.back_button", lang), callback_data=callbacks.build(ns, "back"))],
        ]
    )


def edit_field_keyboard(lang: str, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("agenda.edit_title_button", lang), callback_data=callbacks.build(ns, "editfield", f"{idx}:title")),
                InlineKeyboardButton(t("agenda.edit_when_button", lang), callback_data=callbacks.build(ns, "editfield", f"{idx}:when")),
            ],
            [InlineKeyboardButton(t("agenda.cancel_button", lang), callback_data=callbacks.build(ns, "ev", str(idx)))],
        ]
    )


def delete_confirm_keyboard(lang: str, idx: int) -> InlineKeyboardMarkup:
    arg = str(idx)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("agenda.delete_yes_button", lang), callback_data=callbacks.build(ns, "delyes", arg)),
                InlineKeyboardButton(t("agenda.cancel_button", lang), callback_data=callbacks.build(ns, "ev", arg)),
            ]
        ]
    )
