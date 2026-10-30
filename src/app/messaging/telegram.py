from __future__ import annotations

import logging
from typing import Optional

import telegram

from ..services.qa import QAService

logger = logging.getLogger(__name__)
_ERROR_ANSWER = "I couldn't answer that right now. Please try again later."


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
        try:
            result = await self.qa.answer(str(chat_id), message.text)
            answer = result.answer
        except Exception:
            logger.exception("failed to answer Telegram update %s", update.update_id)
            answer = _ERROR_ANSWER

        if self.bot is not None:
            await self.bot.send_message(chat_id=chat_id, text=answer)
        return answer

    async def send_message(self, chat_id, text) -> None:
        if self.bot is not None:
            await self.bot.send_message(chat_id=chat_id, text=text)
