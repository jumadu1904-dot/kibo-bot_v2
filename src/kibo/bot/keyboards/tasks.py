from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from kibo.bot import callbacks
from kibo.i18n import t
from kibo.services.tasks import TaskView

ns = callbacks.NAMESPACE_TASKS


def tasks_list_keyboard(lang: str, tasks: list[TaskView]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"☐ {task.title}", callback_data=callbacks.build(ns, "done", task.id))]
        for task in tasks
    ]
    rows.append([InlineKeyboardButton(t("tasks.add_button", lang), callback_data=callbacks.build(ns, "add"))])
    rows.append(
        [
            InlineKeyboardButton(t("menu.back_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
            InlineKeyboardButton(t("menu.home_button", lang), callback_data=callbacks.build(callbacks.NAMESPACE_MENU, "home")),
        ]
    )
    return InlineKeyboardMarkup(rows)
