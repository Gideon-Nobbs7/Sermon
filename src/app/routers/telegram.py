import logging

from fastapi import APIRouter, Request

from ..config import settings
from ..db.database import claim_telegram_update
from ..errors import AppError

router = APIRouter()
logger = logging.getLogger(__name__)


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
    update_id = payload.get("update_id")
    if type(update_id) is not int:
        raise AppError(400, "Invalid Telegram update", "telegram_invalid_update")

    if not await claim_telegram_update(update_id, db_path=request.app.state.db_path):
        logger.info("ignoring duplicate Telegram update %s", update_id)
        return {"ok": True}

    try:
        await messenger.handle_update(payload)
    except Exception:
        logger.exception("failed to handle Telegram update %s", update_id)
    return {"ok": True}
