from __future__ import annotations

import logging

from .context import get_request_id

_FORMAT = "%(asctime)s %(levelname)s %(request_id)s%(name)s: %(message)s"


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RequestContextFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", None)
        record.request_id = f"[{rid}] " if rid else ""
        try:
            return super().format(record)
        finally:
            record.request_id = rid


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(RequestContextFormatter(_FORMAT))
    handler.addFilter(RequestContextFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())