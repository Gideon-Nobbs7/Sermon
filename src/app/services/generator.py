from __future__ import annotations

from typing import List, Optional

import httpx

from ..config import settings
from ..errors import AppError
from ..schemas.sermon import Chunk


SYSTEM_PROMPT = """
You are a helpful assistant that answers questions about church sermons.
Answer based ONLY on the provided context. Be precise and concise.
Always cite the sermon date and speaker in your answer.
If the context does not contain enough information, say so.
Do not make up or extrapolate beyond the given context.
"""


def build_user_message(chunks: List[Chunk], question: str) -> str:
    blocks = "\n".join(
        f"<context>\n"
        f"Date: {c.date} | Speaker: {c.speaker} | Topic: {c.topic_title} | "
        f"Scriptures: {', '.join(c.scriptures)}\n"
        f"Notes: {c.text}\n"
        f"</context>"
        for c in chunks
    )
    return f"Context:\n{blocks}\n\nQuestion:\n{question}"


class Generator:
    """Answers grounded in retrieved chunks via the DeepSeek chat API."""

    def __init__(
        self,
        api_key: str = "",
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_BASE_URL
        self.model = model or settings.LLM_MODEL

    def build_messages(
        self,
        chunks: List[Chunk],
        question: str,
        history: Optional[List[dict]] = None,
    ) -> List[dict]:
        messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": build_user_message(chunks, question)})
        return messages

    async def generate(
        self,
        chunks: List[Chunk],
        question: str,
        history: Optional[List[dict]] = None,
    ) -> str:
        if not self.api_key:
            raise AppError(
                500,
                "LLM_API_KEY has not been set. Add it to enable question answering.",
                "llm_api_key_missing",
            )
        payload = {
            "model": self.model,
            "messages": self.build_messages(chunks, question, history),
            "temperature": 0.0,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]