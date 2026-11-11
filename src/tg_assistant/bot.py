"""aiogram 3 glue: turns Telegram updates into Assistant calls."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from .assistant import Assistant
from .booking import Reply
from .config import Settings, load_business
from .db import Database
from .knowledge import KnowledgeBase
from .llm import OpenAICompatibleClient
from .ratelimit import RateLimiter

log = logging.getLogger(__name__)
_COMMANDS = ["start", "help", "book", "lead", "contact", "human", "cancel", "services", "hours"]


def build_assistant(settings: Settings) -> Assistant:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    llm = (
        OpenAICompatibleClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
        if settings.llm_enabled
        else None
    )
    return Assistant(
        config=load_business(settings.business_path),
        kb=KnowledgeBase.from_file(settings.knowledge_path),
        db=Database(settings.db_path),
        limiter=RateLimiter(settings.rate_limit, settings.rate_window_s),
        llm=llm,
    )


def _keyboard(reply: Reply) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if not reply.options:
        return ReplyKeyboardRemove()
    rows = [[KeyboardButton(text=o)] for o in reply.options]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def build_dispatcher(assistant: Assistant, bot: Bot, settings: Settings) -> Dispatcher:
    dp = Dispatcher()
    admin_id = settings.admin_chat_id

    def is_admin(message: Message) -> bool:
        if admin_id is None:
            return False
        user_id = message.from_user.id if message.from_user else None
        return message.chat.id == admin_id or user_id == admin_id

    async def send(message: Message, reply: Reply) -> None:
        if reply.text:
            await message.answer(reply.text, reply_markup=_keyboard(reply))
        if reply.admin_notice and admin_id is not None:
            await bot.send_message(admin_id, reply.admin_notice)

    @dp.message(Command("export"))
    async def export(message: Message) -> None:
        if not is_admin(message):
            await message.answer("Owner only.")
            return
        for kind in ("leads", "bookings"):
            data = assistant.export_csv(kind).encode("utf-8-sig")
            await message.answer_document(BufferedInputFile(data, filename=f"{kind}.csv"))

    @dp.message(Command("reply"))
    async def relay(message: Message, command: CommandObject) -> None:
        if not is_admin(message):
            return
        parts = (command.args or "").split(maxsplit=1)
        if len(parts) != 2 or not parts[0].lstrip("-").isdigit():
            await message.answer("Usage: /reply <user_id> <text>")
            return
        await bot.send_message(int(parts[0]), parts[1])
        await message.answer("Sent.")

    @dp.message(Command(*_COMMANDS))
    async def command(message: Message, command: CommandObject) -> None:
        user = message.from_user
        if user is None:
            return
        reply = await assistant.on_command(
            user.id, command.command, user.username or "", user.full_name
        )
        await send(message, reply)

    @dp.message(F.text)
    async def text(message: Message) -> None:
        user = message.from_user
        if user is None or message.text is None:
            return
        reply = await assistant.on_message(
            user.id, message.text, user.username or "", user.full_name
        )
        await send(message, reply)

    return dp


async def run(settings: Settings) -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
    bot = Bot(settings.bot_token)
    assistant = build_assistant(settings)
    dp = build_dispatcher(assistant, bot, settings)
    log.info("Bot started (LLM %s)", "on" if settings.llm_enabled else "off")
    await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings.from_env()))
