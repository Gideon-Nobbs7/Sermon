from __future__ import annotations

from html import escape

from ..services.qa import QAService


class WhatsAppMessenger:
    """
    Scaffold for the Whatsapp integration.
    """

    def __init__(self, qa_service: QAService):
        self.qa = qa_service

    async def handle_update(self, payload: dict) -> str:
        body = payload.get("Body") or ""
        sender = payload.get("From") or "unknown"
        result = await self.qa.answer(sender, body)
        return f"<Response><Message>{escape(result.answer)}</Message></Response>"

    async def send_message(self, chat_id, text) -> None:
        raise NotImplementedError("WhatsApp integration incoming")