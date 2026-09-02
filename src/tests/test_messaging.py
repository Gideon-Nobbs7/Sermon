from unittest.mock import AsyncMock

import pytest
import telegram

from src.app.messaging.telegram import TelegramMessenger
from src.app.messaging.whatsapp import WhatsAppMessenger
from src.app.schemas.qa import Answer

TELEGRAM_UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 10,
        "date": 1756800000,
        "from": {"id": 123, "is_bot": False, "first_name": "G"},
        "chat": {"id": 123, "type": "private"},
        "text": "hello",
    },
}


class FakeQA:
    def __init__(self):
        self.calls = []

    async def answer(self, session_id, question, k=None):
        self.calls.append((session_id, question))
        return Answer(answer="reply from qa", sources=[])


def test_telegram_parses_update_and_replies(monkeypatch):
    qa = FakeQA()
    bot = telegram.Bot(token="123:fake")
    send = AsyncMock()
    monkeypatch.setattr(telegram.Bot, "send_message", send)
    messenger = TelegramMessenger(qa_service=qa, bot=bot)

    import asyncio

    reply = asyncio.run(messenger.handle_update(TELEGRAM_UPDATE))

    assert reply == "reply from qa"
    assert qa.calls == [("123", "hello")]
    send.assert_awaited_once_with(chat_id=123, text="reply from qa")


def test_telegram_ignores_non_text_updates():
    qa = FakeQA()
    messenger = TelegramMessenger(qa_service=qa)
    payload = {"update_id": 2, "message": {"message_id": 1, "date": 1756800000, "chat": {"id": 1, "type": "private"}}}

    import asyncio

    assert asyncio.run(messenger.handle_update(payload)) is None
    assert qa.calls == []


def test_whatsapp_returns_twiml_and_answers():
    qa = FakeQA()
    messenger = WhatsAppMessenger(qa_service=qa)

    import asyncio

    twiml = asyncio.run(messenger.handle_update({"From": "whatsapp:+1555", "Body": "hello"}))

    assert twiml == "<Response><Message>reply from qa</Message></Response>"
    assert qa.calls == [("whatsapp:+1555", "hello")]


def test_whatsapp_escapes_answer_content():
    qa = FakeQA()
    qa.answer = AsyncMock(return_value=Answer(answer="a <b> & b", sources=[]))
    messenger = WhatsAppMessenger(qa_service=qa)

    import asyncio

    twiml = asyncio.run(messenger.handle_update({"From": "x", "Body": "hi"}))
    assert "&lt;b&gt;" in twiml


def test_whatsapp_send_is_stubbed():
    with pytest.raises(NotImplementedError):
        import asyncio

        asyncio.run(WhatsAppMessenger(FakeQA()).send_message("x", "y"))