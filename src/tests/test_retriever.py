from src.app.db.database import get_connection, init_db, serialize_embedding
from src.app.schemas.sermon import SourceType
from src.app.services.retriever import Retriever


class FixedEmbeddingService:
    model = "fixed"
    dimensions = 3

    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def aembed(self, texts):
        return self.embed(texts)


def _seed(db_path):
    conn = get_connection(str(db_path))
    init_db(conn, dimensions=3)

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

    vectors = {
        "chunk_a": [0.1, 0.2, 0.3],   # identical to query -> distance 0
        "chunk_b": [1.0, 0.0, 0.0],   # farther away
    }
    for cid, vec in vectors.items():
        conn.execute(
            "INSERT INTO chunks_embeddings (chunk_id, embedding) VALUES (?, ?)",
            (cid, serialize_embedding(vec)),
        )
    conn.commit()
    conn.close()


def test_retrieve_returns_ranked_chunks(tmp_path):
    db = tmp_path / "retriever.db"
    _seed(db)

    retriever = Retriever(FixedEmbeddingService(), db_path=str(db), default_k=5)
    import asyncio

    results = asyncio.run(retriever.retrieve("the spirit of excellence"))

    assert [c.id for c in results] == ["chunk_a", "chunk_b"]
    assert results[0].speaker == "Ps. Derrick"
    assert results[0].date == "2026-02-08"
    assert results[0].scriptures == ["1:1"]


def test_retrieve_respects_k(tmp_path):
    db = tmp_path / "retriever.db"
    _seed(db)

    retriever = Retriever(FixedEmbeddingService(), db_path=str(db), default_k=5)
    import asyncio

    results = asyncio.run(retriever.retrieve("q", k=1))
    assert [c.id for c in results] == ["chunk_a"]


def test_retrieve_empty_corpus(tmp_path):
    db = tmp_path / "empty.db"
    conn = get_connection(str(db))
    init_db(conn, dimensions=3)
    conn.close()

    retriever = Retriever(FixedEmbeddingService(), db_path=str(db), default_k=5)
    import asyncio

    assert asyncio.run(retriever.retrieve("q")) == []