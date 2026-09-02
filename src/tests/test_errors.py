import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.app.context import request_scope
from src.app.errors import AppError, register_exception_handlers
from src.app.logging import RequestContextFilter


def test_app_error_fields():
    exc = AppError(404, "Not found", "chunk_missing")
    assert exc.status_code == 404
    assert exc.detail == "Not found"
    assert exc.error == "chunk_missing"
    assert str(exc) == "Not found"


def _app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/app-error")
    async def app_error():
        raise AppError(404, "Sermon not found", "chunk_missing")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @app.get("/bad")
    async def bad(query: int):
        return query

    return app


def test_app_error_response_shape():
    client = TestClient(_app())
    resp = client.get("/app-error")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Sermon not found"}


def test_unhandled_error_does_not_leak():
    client = TestClient(_app(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
    assert "kaboom" not in resp.text


def test_validation_error_is_422():
    client = TestClient(_app())
    resp = client.get("/bad?query=abc")
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_app_error_logged_with_request_id(caplog):
    caplog.set_level(logging.ERROR, logger="app.errors")
    caplog.handler.addFilter(RequestContextFilter())

    client = TestClient(_app())
    with request_scope(request_id="req_1234abcd"):
        client.get("/app-error")

    records = [r for r in caplog.records if r.request_id == "req_1234abcd"]
    assert records, "expected a log record tagged with the request id"
    assert "chunk_missing" in records[0].message