from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t
from kibo.services.calendar import CalendarView

ns = callbacks.NAMESPACE_CALENDAR


def calendar_choice_keyboard(lang: str, pending_id: int, event_index: int, calendars: list[CalendarView]) -> InlineKeyboardMarkup:
    """Two buttons per row — same layout as kibo.bot.keyboards.tasklist for
    the equivalent "which list" picker."""
    buttons = [
        InlineKeyboardButton(item.summary, callback_data=callbacks.build(ns, "pick", f"{pending_id}:{event_index}:{i}"))
        for i, item in enumerate(calendars)
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [InlineKeyboardButton(t("smart_input.cancel_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_CONFIRM, "no", str(pending_id)))]
    )
    return InlineKeyboardMarkup(rows)
