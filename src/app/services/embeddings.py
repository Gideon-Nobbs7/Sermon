from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import List, Optional, Protocol

import httpx

from ..config import settings
from ..errors import AppError

logger = logging.getLogger("embeddings")

_MAX_RETRIES = 3
_RETRY_BASE_SECONDS = 1.0
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def _retry_delay(attempt: int, retry_after: Optional[float] = None) -> float:
    """Exponential backoff with jitter"""
    if retry_after is not None and retry_after >= 0:
        return retry_after + random.uniform(0, 0.5)
    return _RETRY_BASE_SECONDS * (2**attempt) + random.uniform(0, 0.5)


def _retry_after_seconds(exc: httpx.HTTPStatusError) -> Optional[float]:
    try:
        value = exc.response.headers.get("retry-after")
    except Exception:
        return None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            status = exc.response.status_code
        except Exception:
            return False
        return status in _RETRYABLE_STATUSES
    return False


class EmbeddingService(Protocol):
    model: str
    dimensions: int

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Return one embedding vector per input text."""
        ...

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        """Async variant for use inside the request pipeline."""
        ...


class OpenAIEmbeddingService:

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        url: Optional[str] = None,
        key_env: str = "OPENAI_API_KEY",
        timeout: Optional[float] = None,
    ):
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._url = url or settings.OPENAI_EMBEDDINGS_URL
        self._key_env = key_env
        self._timeout = timeout if timeout is not None else settings.EMBEDDING_TIMEOUT_SECONDS

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    @staticmethod
    def _extract(payload: dict) -> List[List[float]]:
        if payload.get("error"):
            raise AppError(502, "Embedding provider reported an error", "embedding_reported_error")
        items = payload.get("data")
        if not items:
            raise AppError(502, "Embedding provider returned no data", "embedding_no_data")
        return [item["embedding"] for item in items]

    def _require_key(self) -> None:
        if not self._api_key:
            raise AppError(
                500,
                f"{self._key_env} has not been set. Add it to enable corpus and question embedding.",
                f"{self._key_env.lower()}_missing",
            )

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._require_key()
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = httpx.post(
                    self._url,
                    headers=self._headers(self._api_key),
                    json={"model": self.model, "input": texts},
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return self._extract(resp.json())
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not _is_retryable(exc) or attempt == _MAX_RETRIES - 1:
                    raise
                retry_after = (
                    _retry_after_seconds(exc)
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None
                )
                delay = _retry_delay(attempt, retry_after)
                logger.warning(
                    "embedding provider %s attempt %d/%d failed (%s), "
                    "retrying in %.1fs",
                    self.model,
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        self._require_key()
        last_exc: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await client.post(
                        self._url,
                        headers=self._headers(self._api_key),
                        json={"model": self.model, "input": texts},
                    )
                    resp.raise_for_status()
                    return self._extract(resp.json())
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if not _is_retryable(exc) or attempt == _MAX_RETRIES - 1:
                        raise
                    retry_after = (
                        _retry_after_seconds(exc)
                        if isinstance(exc, httpx.HTTPStatusError)
                        else None
                    )
                    delay = _retry_delay(attempt, retry_after)
                    logger.warning(
                        "embedding provider %s attempt %d/%d failed (%s), "
                        "retrying in %.1fs",
                        self.model,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc


class StubEmbeddingService:
    """Zero vectors it is only useful for tests and offline seeding."""

    def __init__(self, dimensions: int = 1536):
        self.model = "stub"
        self.dimensions = dimensions

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] * self.dimensions for _ in texts]

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        return self.embed(texts)