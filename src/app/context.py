"""
Async code can interleave; contextvars keep each task's lifecycle
separate so a request's id and metadata never leak into another.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator, Optional

request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:8]}"


def get_request_id() -> Optional[str]:
    return request_context.get().get("request_id")


def get_context() -> dict[str, Any]:
    return request_context.get()


@contextmanager
def request_scope(**fields: Any) -> Iterator[None]:
    """Run a block with extra fields merged into the request context.

    Always resets the contextvar on exit so a task cannot leak its
    lifecycle into a sibling task.
    """
    token: Token = request_context.set({**request_context.get(), **fields})
    try:
        yield
    finally:
        request_context.reset(token)