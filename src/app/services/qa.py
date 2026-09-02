from __future__ import annotations

from typing import List, Optional

from ..schemas.qa import Answer
from ..schemas.sermon import Chunk
from .generator import Generator
from .history import ChatHistoryStore
from .retriever import Retriever

_NOT_FOUND = "I couldn't find anything on that in the sermons I have."


class QAService:
    """Orchestrates history -> retrieval -> generation -> persistence."""

    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        history: ChatHistoryStore,
        default_k: int = 5,
    ):
        self.retriever = retriever
        self.generator = generator
        self.history = history
        self.default_k = default_k

    async def answer(self, session_id: str, question: str, k: Optional[int] = None) -> Answer:
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
        "source_file": chunk.source_file,
        "page": chunk.page,
    }