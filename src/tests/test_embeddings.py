import asyncio
from unittest.mock import Mock

import httpx

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