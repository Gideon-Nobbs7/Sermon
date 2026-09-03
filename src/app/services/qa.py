from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from ..config import settings
from ..schemas.qa import Answer
from ..schemas.sermon import Chunk
from .generator import Generator
from .history import ChatHistoryStore
from .retriever import Retriever

logger = logging.getLogger("app.qa")

_NOT_FOUND = "I couldn't find anything on that in the sermons I have."
_SLOW = "This is taking longer than expected - please try again in a moment."


class QAService:
    """Orchestrates history -> retrieval -> generation -> persistence."""

    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        history: ChatHistoryStore,
        default_k: int = 5,
        timeout: Optional[float] = None,
    ):
        self.retriever = retriever
        self.generator = generator
        self.history = history
        self.default_k = default_k
        self.timeout = timeout if timeout is not None else settings.QA_TIMEOUT_SECONDS

    async def answer(self, session_id: str, question: str, k: Optional[int] = None) -> Answer:
        try:
            return await asyncio.wait_for(
                self._answer(session_id, question, k), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.warning("qa pipeline timed out after %ss", self.timeout)
            await self._record(session_id, question, _SLOW)
            return Answer(answer=_SLOW, sources=[])

    async def _answer(self, session_id: str, question: str, k: Optional[int]) -> Answer:
        turns = await self.history.recent(session_id)
        query = self._retrieval_query(turns, question)

        chunks = await self.retriever.retrieve(query, k or self.default_k)
        if not chunks:
            await self._record(session_id, question, _NOT_FOUND)
            return Answer(answer=_NOT_FOUND, sources=[])

        answer_text = await self.generator.generate(chunks, question, history=turns)
        await self._record(session_id, question, answer_text)
        return Answer(answer=answer_text, sources=[_source(c) for c in chunks])

    @staticmethod
    def _retrieval_query(turns: List[dict], question: str) -> str:
        last_user = next(
            (t["content"] for t in reversed(turns) if t["role"] == "user"), None
        )
        return f"{last_user} {question}" if last_user else question

    async def _record(self, session_id: str, question: str, answer: str) -> None:
        await self.history.append(session_id, "user", question)
        await self.history.append(session_id, "assistant", answer)


def _source(chunk: Chunk) -> dict:
    return {
        "date": chunk.date,
        "speaker": chunk.speaker,
        "topic": chunk.topic_title,
        "scriptures": chunk.scriptures,
        "source_file": chunk.source_file,
        "page": chunk.page,
    }