from telegram import Update
from telegram.ext import ContextTypes

from kibo.bot.keyboards.menu import back_home_keyboard
from kibo.db.models import User
from kibo.db.repositories import users
from kibo.db.session import get_sessionmaker
from kibo.services import briefing as briefing_service


async def _render(user: User) -> str:
    async with get_sessionmaker()() as session:
        return await briefing_service.build(session, user)


async def send(message, user: User) -> None:
    await message.reply_text(await _render(user), reply_markup=back_home_keyboard(user.lang))


async def edit(query, user: User) -> None:
    await query.edit_message_text(await _render(user), reply_markup=back_home_keyboard(user.lang))


async def briefing_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/briefing_now — debug command to see today's briefing immediately,
    without waiting for `briefing_time` (see docs/ARCHITECTURE.md F4)."""
    async with get_sessionmaker()() as session:
        user = await users.get_by_telegram_id(session, update.effective_user.id)
    if user is None:
        return
    await send(update.effective_message, user)
