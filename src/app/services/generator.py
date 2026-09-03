from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import httpx

from ..config import settings
from ..errors import AppError
from ..schemas.sermon import Chunk

logger = logging.getLogger("app.generator")

SYSTEM_PROMPT = """
You are a helpful assistant that answers questions about church sermons.
Answer based ONLY on the provided context. Be precise and concise.
Always cite the sermon date and speaker in your answer.
If the context does not contain enough information, say so.
Do not make up or extrapolate beyond the given context.
"""


@dataclass
class LLMProvider:
    name: str
    base_url: str
    api_key: str
    model: str
    key_env: str
    extra_body: dict = field(default_factory=dict)


def default_providers() -> List[LLMProvider]:
    return [
        LLMProvider(
            name="deepseek",
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            key_env="LLM_API_KEY",
            extra_body={"thinking": {"type": "disabled"}},
        ),
        LLMProvider(
            name="openrouter",
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_LLM_MODEL,
            key_env="OPENROUTER_API_KEY",
        ),
    ]


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
    """Answers grounded in retrieved chunks via one of several LLM providers.

    DeepSeek is tried first and OpenRouter is the fallback.
    """

    def __init__(
        self,
        providers: Optional[Sequence[LLMProvider]] = None,
        timeout: Optional[float] = None,
        retries: int = 2,
    ):
        self.providers = list(providers) if providers else default_providers()
        self.timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS
        self.retries = retries

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
        messages = self.build_messages(chunks, question, history)
        errors: List[Exception] = []

        for provider in self.providers:
            if not provider.api_key:
                continue
            for attempt in range(self.retries):
                try:
                    return await self._call(provider, messages)
                except Exception as exc:
                    logger.warning(
                        "llm provider %s attempt %d/%d failed: %s",
                        provider.name, attempt + 1, self.retries, exc,
                    )
                    errors.append(exc)
                    if attempt < self.retries - 1:
                        await asyncio.sleep(0.5 * (attempt + 1))

        first_app_error = next((e for e in errors if isinstance(e, AppError)), None)
        if first_app_error is not None:
            raise first_app_error
        if errors:
            raise AppError(
                502, "Answer generation failed - all providers errored.", "llm_all_failed"
            )
        raise AppError(
            500,
            "No LLM provider is configured - set LLM_API_KEY or OPENROUTER_API_KEY.",
            "llm_no_provider",
        )

    async def _call(self, provider: LLMProvider, messages: List[dict]) -> str:
        payload = {
            "model": provider.model,
            "messages": messages,
            "temperature": 0.0,
            "stream": False,
            **provider.extra_body,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{provider.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {provider.api_key}"},
                json=payload,
            )
        resp.raise_for_status()

        body = resp.json()
        if body.get("error"):
            message = body["error"].get("message") or str(body["error"])
            logger.warning("llm provider %s reported an error: %s", provider.name, message)
            raise AppError(502, f"{provider.name} reported an error", f"{provider.name}_reported_error")
        choices = body.get("choices") or []
        if not choices:
            raise AppError(502, f"{provider.name} returned no choices", f"{provider.name}_no_choices")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise AppError(502, f"{provider.name} returned empty content", f"{provider.name}_empty_content")
        return content