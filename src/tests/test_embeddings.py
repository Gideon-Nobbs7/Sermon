import asyncio
from unittest.mock import Mock

import httpx
import pytest

from src.app.errors import AppError
from src.app.services.embeddings import OpenAIEmbeddingService


def _fake_response(vectors):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"data": [{"embedding": v} for v in vectors]}
    return resp


def test_sync_embed_posts_and_extracts(monkeypatch):
    posted = {}

    def fake_post(url, headers, json, timeout):
        posted["url"] = url
        posted["json"] = json
        assert headers["Authorization"] == "Bearer sk-test"
        return _fake_response([[0.1, 0.2], [0.3, 0.4]])

    monkeypatch.setattr(httpx, "post", fake_post)

    svc = OpenAIEmbeddingService(api_key="sk-test", model="text-embedding-3-small", dimensions=2)
    out = svc.embed(["one", "two"])

    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert posted["url"].endswith("/v1/embeddings")
    assert posted["json"]["model"] == "text-embedding-3-small"
    assert posted["json"]["input"] == ["one", "two"]


def test_async_aembed_posts_and_extracts(monkeypatch):
    async def fake_post(self, url, headers, json):
        assert headers["Authorization"] == "Bearer sk-test"
        return _fake_response([[0.5], [0.6]])

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    svc = OpenAIEmbeddingService(api_key="sk-test", dimensions=1)

    async def main():
        return await svc.aembed(["q1", "q2"])

    assert asyncio.run(main()) == [[0.5], [0.6]]


def test_embed_requires_api_key():
    svc = OpenAIEmbeddingService(api_key="")
    with pytest.raises(AppError, match="OPENAI_API_KEY"):
        svc.embed(["q"])


def test_aembed_requires_api_key():
    svc = OpenAIEmbeddingService(api_key="")
    with pytest.raises(AppError, match="OPENAI_API_KEY"):
        asyncio.run(svc.aembed(["q"]))


def test_key_env_names_the_right_setting():
    svc = OpenAIEmbeddingService(api_key="", key_env="OPENROUTER_API_KEY")
    with pytest.raises(AppError, match="OPENROUTER_API_KEY"):
        svc.embed(["q"])


def test_openrouter_embed_uses_custom_url_and_model(monkeypatch):
    posted = {}

    def fake_post(url, headers, json, timeout):
        posted["url"] = url
        posted["json"] = json
        return _fake_response([[0.1, 0.2]])

    monkeypatch.setattr(httpx, "post", fake_post)

    svc = OpenAIEmbeddingService(
        api_key="sk-or",
        model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        dimensions=1024,
        url="https://openrouter.ai/api/v1/embeddings",
        key_env="OPENROUTER_API_KEY",
    )
    svc.embed(["q"])

    assert posted["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert posted["json"]["model"] == "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    assert posted["json"]["input"] == ["q"]


def test_embed_raises_clean_error_on_error_body(monkeypatch):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"error": {"message": "rate limited"}}

    def fake_post(url, headers, json, timeout):
        return resp

    monkeypatch.setattr(httpx, "post", fake_post)

    svc = OpenAIEmbeddingService(api_key="sk-test")
    with pytest.raises(AppError, match="Embedding provider reported an error"):
        svc.embed(["q"])


def _status_error(status, retry_after=None):
    request = httpx.Request("POST", "https://provider.test/v1/embeddings")
    headers = {"retry-after": str(retry_after)} if retry_after is not None else None
    response = httpx.Response(status, headers=headers, request=request)
    return httpx.HTTPStatusError(f"status {status}", request=request, response=response)


def test_embed_retries_429_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(json)
        if len(calls) < 3:
            raise _status_error(429)
        return _fake_response([[0.9]])

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("src.app.services.embeddings.time.sleep", lambda s: None)

    svc = OpenAIEmbeddingService(api_key="sk-test", dimensions=1)
    assert svc.embed(["q"]) == [[0.9]]
    assert len(calls) == 3


def test_embed_gives_up_after_exhausting_retries(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(1)
        raise _status_error(429)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("src.app.services.embeddings.time.sleep", lambda s: None)

    svc = OpenAIEmbeddingService(api_key="sk-test")
    with pytest.raises(httpx.HTTPStatusError):
        svc.embed(["q"])
    assert len(calls) == 3


def test_embed_does_not_retry_client_errors(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(1)
        raise _status_error(400)

    monkeypatch.setattr(httpx, "post", fake_post)

    svc = OpenAIEmbeddingService(api_key="sk-test")
    with pytest.raises(httpx.HTTPStatusError):
        svc.embed(["q"])
    assert len(calls) == 1


def test_embed_honors_retry_after(monkeypatch):
    seen_delays = []

    def fake_post(url, headers, json, timeout):
        if len(seen_delays) == 0:
            seen_delays.append(0)
            raise _status_error(429, retry_after=7)
        return _fake_response([[0.1]])

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(
        "src.app.services.embeddings.time.sleep", lambda s: seen_delays.append(s)
    )

    svc = OpenAIEmbeddingService(api_key="sk-test", dimensions=1)
    assert svc.embed(["q"]) == [[0.1]]
    assert seen_delays[1] >= 7