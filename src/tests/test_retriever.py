import asyncio

import pytest

from src.app.db.database import get_connection, init_db, serialize_embedding
from src.app.errors import AppError
from src.app.schemas.sermon import SourceType
from src.app.services.retriever import Retriever

PRIMARY_DIM = 4
FALLBACK_DIM = 3


class FakeEmbeddingService:
    def __init__(self, vector, model="fake", fail=False, app_error=False):
        self.vector = vector
        self.model = model
        self.dimensions = len(vector)
        self.fail = fail
        self.app_error = app_error

    def embed(self, texts):
        return self.embed_sync(texts)

    def embed_sync(self, texts):
        if self.fail:
            if self.app_error:
                raise AppError(500, "OPENAI_API_KEY has not been set", "openai_api_key_missing")
            raise RuntimeError("connection refused")
        return [self.vector for _ in texts]

    async def aembed(self, texts):
        return self.embed_sync(texts)


def _seed(db_path, seed_fallback=True):
    conn = get_connection(str(db_path))
    init_db(conn, dimensions=(PRIMARY_DIM, FALLBACK_DIM))

    rows = [
        ("chunk_a", "2026-02-08", "Ps. Derrick", "Exhortation", "The Spirit of Excellence", '["1:1"]', "close text"),
        ("chunk_b", "2026-02-15", "Ps. Richard", "Rhema", "The Spirit of Might", '["1:2"]', "far text"),
    ]
    for cid, date, speaker, ttype, title, scriptures, text in rows:
        conn.execute(
            "INSERT INTO chunks (id, source_type, source_file, date, speaker, "
            "topic_type, topic_title, scriptures, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, SourceType.SERMON.value, "2026-Sermons.md", date, speaker,
             ttype, title, scriptures, text),
        )

    primary_vectors = {
        "chunk_a": [0.1, 0.2, 0.3, 0.4],   # identical to query -> distance 0
        "chunk_b": [1.0, 0.0, 0.0, 0.0],   # farther away
    }
    for cid, vec in primary_vectors.items():
        conn.execute(
            "INSERT INTO chunks_embeddings_4 (chunk_id, embedding) VALUES (?, ?)",
            (cid, serialize_embedding(vec)),
        )

    if seed_fallback:
        fallback_vectors = {
            "chunk_a": [0.5, 0.5, 0.5],   # identical to fallback query -> distance 0
            "chunk_b": [1.0, 0.0, 0.0],   # farther away
        }
        for cid, vec in fallback_vectors.items():
            conn.execute(
                "INSERT INTO chunks_embeddings_3 (chunk_id, embedding) VALUES (?, ?)",
                (cid, serialize_embedding(vec)),
            )
    conn.commit()
    conn.close()


def _retriever(primary, fallback, db_path, k=5):
    return Retriever(
        [(primary, PRIMARY_DIM), (fallback, FALLBACK_DIM)],
        db_path=str(db_path),
        default_k=k,
    )


def test_retrieve_returns_ranked_chunks(tmp_path):
    db = tmp_path / "retriever.db"
    _seed(db)

    primary = FakeEmbeddingService([0.1, 0.2, 0.3, 0.4])
    fallback = FakeEmbeddingService([0.5, 0.5, 0.5])
    results = asyncio.run(_retriever(primary, fallback, db).retrieve("excellence"))

    assert [c.id for c in results] == ["chunk_a", "chunk_b"]
    assert results[0].speaker == "Ps. Derrick"
    assert results[0].date == "2026-02-08"
    assert results[0].scriptures == ["1:1"]


def test_retrieve_respects_k(tmp_path):
    db = tmp_path / "retriever.db"
    _seed(db)

    primary = FakeEmbeddingService([0.1, 0.2, 0.3, 0.4])
    fallback = FakeEmbeddingService([0.5, 0.5, 0.5])
    results = asyncio.run(_retriever(primary, fallback, db).retrieve("q", k=1))
    assert [c.id for c in results] == ["chunk_a"]


def test_retrieve_empty_corpus(tmp_path):
    db = tmp_path / "empty.db"
    conn = get_connection(str(db))
    init_db(conn, dimensions=(PRIMARY_DIM, FALLBACK_DIM))
    conn.close()

    primary = FakeEmbeddingService([0.1, 0.2, 0.3, 0.4])
    fallback = FakeEmbeddingService([0.5, 0.5, 0.5])
    assert asyncio.run(_retriever(primary, fallback, db).retrieve("q")) == []


def test_falls_back_to_second_provider_when_primary_fails(tmp_path):
    db = tmp_path / "retriever.db"
    _seed(db)

    primary = FakeEmbeddingService([0.1, 0.2, 0.3, 0.4], fail=True)
    fallback = FakeEmbeddingService([0.5, 0.5, 0.5])
    results = asyncio.run(_retriever(primary, fallback, db).retrieve("excellence"))

    assert [c.id for c in results] == ["chunk_a", "chunk_b"]


def test_raises_when_all_providers_fail(tmp_path):
    db = tmp_path / "retriever.db"
    _seed(db)

    primary = FakeEmbeddingService([0.1, 0.2, 0.3, 0.4], fail=True)
    fallback = FakeEmbeddingService([0.5, 0.5, 0.5], fail=True)
    with pytest.raises(AppError, match="All embedding providers failed"):
        asyncio.run(_retriever(primary, fallback, db).retrieve("q"))


def test_app_error_surfaces_when_all_providers_fail(tmp_path):
    db = tmp_path / "retriever.db"
    _seed(db)

    primary = FakeEmbeddingService([0.1, 0.2, 0.3, 0.4], fail=True, app_error=True)
    fallback = FakeEmbeddingService([0.5, 0.5, 0.5], fail=True, app_error=True)
    with pytest.raises(AppError, match="OPENAI_API_KEY has not been set"):
        asyncio.run(_retriever(primary, fallback, db).retrieve("q"))