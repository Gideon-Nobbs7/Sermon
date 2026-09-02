import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """
    status_code: HTTP status to return.
    detail: human-readable message for the client.
    error: developer-facing reason which logged server-side only.
    """

    def __init__(self, status_code: int, detail: str, error: str):
        self.status_code = status_code
        self.detail = detail
        self.error = error
        super().__init__(detail)


def _json_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.error("app error: %s", exc.error, exc_info=(type(exc), exc, exc.__traceback__))
        return _json_response(exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("validation error: %s", exc.errors())
        return _json_response(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc.errors()))

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", exc_info=True)
        return _json_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error"
        )