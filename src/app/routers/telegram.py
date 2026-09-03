from fastapi import APIRouter, Request

from ..config import settings
from ..errors import AppError

router = APIRouter()


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request) -> dict:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise AppError(
            500,
            "Telegram is not configured",
            "telegram_not_configured",
        )

    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if secret and request.headers.get(settings.TELEGRAM_SECRET_HEADER) != secret:
        raise AppError(401, "Invalid webhook secret", "telegram_bad_secret")

    messenger = request.app.state.telegram_messenger
    payload = await request.json()
    await messenger.handle_update(payload)
    return {"ok": True}