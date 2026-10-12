from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t
from kibo.services.tasks import TaskListView

ns = callbacks.NAMESPACE_TASKLIST


def tasklist_choice_keyboard(lang: str, pending_id: int, task_index: int, lists: list[TaskListView]) -> InlineKeyboardMarkup:
    """Two buttons per row — accounts with many subject-based lists (a
    common case, see docs/ARCHITECTURE.md) would otherwise need a very
    tall single column."""
    buttons = [
        InlineKeyboardButton(item.title, callback_data=callbacks.build(ns, "pick", f"{pending_id}:{task_index}:{i}"))
        for i, item in enumerate(lists)
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [InlineKeyboardButton(t("smart_input.cancel_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_CONFIRM, "no", str(pending_id)))]
    )
    return InlineKeyboardMarkup(rows)
