from __future__ import annotations

from typing import Optional

import telegram

from ..services.qa import QAService


class TelegramMessenger:

    def __init__(self, qa_service: QAService, bot_token: str = "", bot=None):
        self.qa = qa_service
        self.bot = bot if bot is not None else (telegram.Bot(token=bot_token) if bot_token else None)

    async def handle_update(self, payload: dict) -> Optional[str]:
        update = telegram.Update.de_json(payload, self.bot)
        message = update.effective_message
        if message is None or not message.text:
            return None

        chat_id = message.chat_id
        result = await self.qa.answer(str(chat_id), message.text)
        if self.bot is not None:
            await self.bot.send_message(chat_id=chat_id, text=result.answer)
        return result.answer

    async def send_message(self, chat_id, text) -> None:
        if self.bot is not None:
            await self.bot.send_message(chat_id=chat_id, text=text)