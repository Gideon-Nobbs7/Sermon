from fastapi.testclient import TestClient

from src.app.config import settings
from src.app.errors import AppError
from src.app.main import create_app
from src.app.schemas.qa import Answer


class FakeQA:
    def __init__(self, result=None, error=None):
        self.result = result or Answer(answer="ans", sources=[{"date": "2026-02-15", "speaker": "Ps. Richard"}])
        self.error = error
        self.calls = []

    async def answer(self, session_id, question, k=None):
        self.calls.append((session_id, question, k))
        if self.error is not None:
            raise self.error
        return self.result


class FakeMessenger:
    def __init__(self, reply="ok"):
        self.reply = reply
        self.payload = None

    async def handle_update(self, payload):
        self.payload = payload
        return self.reply


def _client(tmp_path, qa, raise_server_exceptions=True, whatsapp_reply="ok"):
    app = create_app(
        qa=qa,
        telegram_messenger=FakeMessenger(),
        whatsapp_messenger=FakeMessenger(reply=whatsapp_reply),
        db_path=str(tmp_path / "api.db"),
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_health(tmp_path):
    qa = FakeQA()
    with _client(tmp_path, qa) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


def test_health_reports_db_degraded(tmp_path):
    qa = FakeQA()
    with _client(tmp_path, qa) as client:
        db_file = tmp_path / "api.db"
        db_file.write_bytes(b"not a sqlite database")
        resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "db": "error"}


def test_query_returns_answer_and_sources(tmp_path):
    qa = FakeQA()
    with _client(tmp_path, qa) as client:
        resp = client.post("/query", json={"question": "what was taught?", "k": 3, "session_id": "s1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "ans"
    assert body["sources"][0]["speaker"] == "Ps. Richard"
    assert qa.calls == [("s1", "what was taught?", 3)]


def test_query_validation(tmp_path):
    qa = FakeQA()
    with _client(tmp_path, qa) as client:
        resp = client.post("/query", json={"question": "q", "k": 0})
    assert resp.status_code == 422


def test_telegram_webhook_rejects_bad_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "s3cret")
    qa = FakeQA()
    with _client(tmp_path, qa) as client:
        resp = client.post("/webhook/telegram", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "nope"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid webhook secret"}


def test_telegram_webhook_accepts_secret_and_handles(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "s3cret")
    qa = FakeQA()
    payload = {"update_id": 1, "message": {"message_id": 1, "date": 1756800000, "chat": {"id": 1, "type": "private"}, "text": "hi"}}
    with _client(tmp_path, qa) as client:
        resp = client.post("/webhook/telegram", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_whatsapp_webhook_returns_twiml(tmp_path):
    qa = FakeQA()
    with _client(tmp_path, qa, whatsapp_reply="<Response><Message>hi</Message></Response>") as client:
        resp = client.post("/webhook/whatsapp", data={"From": "whatsapp:+1555", "Body": "hi"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "<Response>" in resp.text


def test_app_error_from_qa_is_propagated(tmp_path):
    qa = FakeQA(error=AppError(404, "Nothing found", "no_chunks"))
    with _client(tmp_path, qa) as client:
        resp = client.post("/query", json={"question": "q"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Nothing found"}


def test_unexpected_error_does_not_leak(tmp_path):
    qa = FakeQA(error=RuntimeError("kaboom"))
    with _client(tmp_path, qa, raise_server_exceptions=False) as client:
        resp = client.post("/query", json={"question": "q"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
    assert "kaboom" not in resp.text