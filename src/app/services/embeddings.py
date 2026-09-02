from __future__ import annotations

from typing import List, Optional, Protocol

import httpx

from ..config import settings


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
    ):
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._url = url or settings.OPENAI_EMBEDDINGS_URL

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    @staticmethod
    def _extract(payload: dict) -> List[List[float]]:
        return [item["embedding"] for item in payload["data"]]

    def embed(self, texts: List[str]) -> List[List[float]]:
        resp = httpx.post(
            self._url,
            headers=self._headers(self._api_key),
            json={"model": self.model, "input": texts},
            timeout=30.0,
        )
        resp.raise_for_status()
        return self._extract(resp.json())

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self._url,
                headers=self._headers(self._api_key),
                json={"model": self.model, "input": texts},
            )
        resp.raise_for_status()
        return self._extract(resp.json())


class StubEmbeddingService:
    """Zero vectors it is only useful for tests and offline seeding."""

    def __init__(self, dimensions: int = 1536):
        self.model = "stub"
        self.dimensions = dimensions

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] * self.dimensions for _ in texts]

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        return self.embed(texts)