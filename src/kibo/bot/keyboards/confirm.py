from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t

ns = callbacks.NAMESPACE_CONFIRM


def confirm_keyboard(lang: str, pending_id: int) -> InlineKeyboardMarkup:
    arg = str(pending_id)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("smart_input.confirm_button", lang), callback_data=callbacks.build(ns, "yes", arg)),
                InlineKeyboardButton(t("smart_input.edit_button", lang), callback_data=callbacks.build(ns, "edit", arg)),
                InlineKeyboardButton(t("smart_input.cancel_button", lang), callback_data=callbacks.build(ns, "no", arg)),
            ]
        ]
    )


def cancel_only_keyboard(lang: str, pending_id: int) -> InlineKeyboardMarkup:
    """Used by a mid-clarification prompt (e.g. "when is it?") that isn't
    itself a button choice — still needs a way out without retyping."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("smart_input.cancel_button", lang), callback_data=callbacks.build(ns, "no", str(pending_id)))]]
    )
