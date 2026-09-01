from __future__ import annotations

from typing import List, Protocol


class EmbeddingService(Protocol):
    model: str
    dimensions: int

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Return one embedding vector per input text."""
        ...


class StubEmbeddingService:
    """Returns zero vectors; real embedding lands in scope 2."""

    def __init__(self, dimensions: int = 1536):
        self.model = "stub"
        self.dimensions = dimensions

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] * self.dimensions for _ in texts]
