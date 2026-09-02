import logging

from src.app.context import new_request_id, request_scope
from src.app.logging import RequestContextFilter, RequestContextFormatter, setup_logging


def test_filter_defaults_request_id_to_none():
    record = logging.LogRecord("name", logging.INFO, "", 0, "msg", None, None)
    assert RequestContextFilter().filter(record)
    assert record.request_id is None


def test_filter_sets_request_id_from_scope():
    record = logging.LogRecord("name", logging.INFO, "", 0, "msg", None, None)
    with request_scope(request_id="abc123"):
        assert RequestContextFilter().filter(record)
        assert record.request_id == "abc123"


def test_emitted_logs_carry_request_id(caplog):
    caplog.set_level(logging.INFO, logger="test.logging")
    caplog.handler.addFilter(RequestContextFilter())
    logger = logging.getLogger("test.logging")

    with request_scope(request_id="req-7"):
        logger.info("indexing chunks")

    assert caplog.records[0].request_id == "req-7"


def test_formatter_omits_tag_when_no_request():
    record = logging.LogRecord("name", logging.INFO, "", 0, "msg", None, None)
    record.request_id = None
    text = RequestContextFormatter("%(request_id)s%(message)s").format(record)
    assert text == "msg"


def test_formatter_includes_tag_with_request():
    record = logging.LogRecord("name", logging.INFO, "", 0, "msg", None, None)
    record.request_id = "req-1"
    text = RequestContextFormatter("%(request_id)s%(message)s").format(record)
    assert text == "[req-1] msg"


def test_setup_logging_is_idempotent():
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers.clear()
    try:
        setup_logging("DEBUG")
        setup_logging("INFO")
        stream = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream) == 1
    finally:
        root.handlers[:] = saved
