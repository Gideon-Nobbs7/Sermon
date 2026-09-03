from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import settings
from .context import new_request_id, request_scope
from .db.database import get_async_db, get_connection, init_db
from .errors import register_exception_handlers
from .logging import setup_logging
from .messaging.telegram import TelegramMessenger
from .messaging.whatsapp import WhatsAppMessenger
from .routers import query, telegram, whatsapp
from .services.embeddings import OpenAIEmbeddingService
from .services.generator import Generator
from .services.history import ChatHistoryStore
from .services.qa import QAService
from .services.retriever import Retriever

logger = logging.getLogger("app")

_REQUIRED_KEYS = {
    "OPENAI_API_KEY": "embeddings",
    "LLM_API_KEY": "DeepSeek answers",
    "OPENROUTER_API_KEY": "OpenRouter fallbacks",
    "TELEGRAM_BOT_TOKEN": "the Telegram bot",
    "TELEGRAM_WEBHOOK_SECRET": "Telegram webhook auth",
    "TELEGRAM_SECRET_HEADER": "Telegram webhook header",
}


def create_app(
    *,
    qa: Optional[QAService] = None,
    telegram_messenger: Optional[TelegramMessenger] = None,
    whatsapp_messenger: Optional[WhatsAppMessenger] = None,
    db_path: Optional[str] = None,
) -> FastAPI:
    built_internally = qa is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.LOG_LEVEL)
        if built_internally:
            for name, purpose in _REQUIRED_KEYS.items():
                if not getattr(settings, name):
                    logger.warning(
                        "%s has not been set - %s will fail until it is added",
                        name,
                        purpose,
                    )
        conn = get_connection(db_path)
        init_db(
            conn,
            dimensions=(
                settings.EMBEDDING_DIMENSIONS,
                settings.OPENROUTER_EMBEDDING_DIMENSIONS,
            ),
        )
        conn.close()
        logger.info("db ready at %s", db_path or settings.SQLITE_DB_PATH)
        yield

    app = FastAPI(title="Sermon QA Bot", lifespan=lifespan)
    register_exception_handlers(app)

    @app.middleware("http")
    async def request_context_middleware(request, call_next):
        with request_scope(request_id=new_request_id()):
            logger.info("%s %s", request.method, request.url.path)
            response = await call_next(request)
            return response

    if qa is None:
        primary_embed = OpenAIEmbeddingService(
            api_key=settings.OPENAI_API_KEY,
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        fallback_embed = OpenAIEmbeddingService(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_EMBEDDING_MODEL,
            dimensions=settings.OPENROUTER_EMBEDDING_DIMENSIONS,
            url=f"{settings.OPENROUTER_BASE_URL}/embeddings",
            key_env="OPENROUTER_API_KEY",
        )
        qa = QAService(
            retriever=Retriever(
                [
                    (primary_embed, settings.EMBEDDING_DIMENSIONS),
                    (fallback_embed, settings.OPENROUTER_EMBEDDING_DIMENSIONS),
                ]
            ),
            generator=Generator(),
            history=ChatHistoryStore(db_path=db_path),
        )
    if telegram_messenger is None:
        telegram_messenger = TelegramMessenger(qa, bot_token=settings.TELEGRAM_BOT_TOKEN)
    if whatsapp_messenger is None:
        whatsapp_messenger = WhatsAppMessenger(qa)

    app.state.qa = qa
    app.state.telegram_messenger = telegram_messenger
    app.state.whatsapp_messenger = whatsapp_messenger

    app.include_router(query.router)
    app.include_router(telegram.router)
    app.include_router(whatsapp.router)

    @app.get("/health")
    async def health():
        try:
            async with get_async_db(db_path) as conn:
                await conn.execute("SELECT 1 FROM chunks LIMIT 1")
        except Exception:
            logger.exception("health check: db unavailable")
            return JSONResponse(status_code=503, content={"status": "degraded", "db": "error"})
        return {"status": "ok", "db": "ok"}

    return app


app = create_app()