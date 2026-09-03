import asyncio

from src.app.db.database import (
    get_async_connection,
    get_connection,
    init_async_db,
    init_db,
    serialize_embedding,
)
from src.app.schemas.sermon import SourceType


def test_init_db_creates_tables(tmp_path):
    db = tmp_path / "test.db"
    conn = get_connection(str(db))
    init_db(conn)
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    }
    assert "chunks" in tables
    assert "chunks_embeddings_1536" in tables
    assert "chunks_embeddings_2048" in tables

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(chunks_embeddings_1536)")}
    assert "embedding" in cols
    conn.close()


def test_insert_and_query(tmp_path):
    db = tmp_path / "test.db"
    conn = get_connection(str(db))
    init_db(conn)

    conn.execute(
        "INSERT INTO chunks (id, source_type, source_file, date, speaker, "
        "topic_type, topic_title, scriptures, text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("2026-02-08_exhortation_0", SourceType.SERMON.value, "2026-Sermons.md",
         "2026-02-08", "Ps. Derrick", "Exhortation",
         "The Spirit of Excellence", None, "note text"),
    )
    vec = serialize_embedding([0.1] * 1536)
    conn.execute(
        "INSERT INTO chunks_embeddings_1536 (chunk_id, embedding) VALUES (?, ?)",
        ("2026-02-08_exhortation_0", vec),
    )
    conn.commit()

    row = conn.execute("SELECT id, speaker FROM chunks").fetchone()
    assert row["id"] == "2026-02-08_exhortation_0"
    assert row["speaker"] == "Ps. Derrick"

    k = conn.execute(
        "SELECT chunk_id, distance FROM chunks_embeddings_1536 "
        "WHERE embedding MATCH ? AND k = 5 ORDER BY distance",
        (serialize_embedding([0.1] * 1536),),
    ).fetchone()
    assert k["chunk_id"] == "2026-02-08_exhortation_0"
    conn.close()


def test_query_2048_table(tmp_path):
    db = tmp_path / "test.db"
    conn = get_connection(str(db))
    init_db(conn)

    conn.execute(
        "INSERT INTO chunks (id, source_type, source_file, date, speaker, text) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("2026-02-15_rhema_0", SourceType.SERMON.value, "2026-Sermons.md",
         "2026-02-15", "Ps. Richard", "note"),
    )
    vec = serialize_embedding([0.2] * 2048)
    conn.execute(
        "INSERT INTO chunks_embeddings_2048 (chunk_id, embedding) VALUES (?, ?)",
        ("2026-02-15_rhema_0", vec),
    )
    conn.commit()

    k = conn.execute(
        "SELECT chunk_id, distance FROM chunks_embeddings_2048 "
        "WHERE embedding MATCH ? AND k = 5 ORDER BY distance",
        (serialize_embedding([0.2] * 2048),),
    ).fetchone()
    assert k["chunk_id"] == "2026-02-15_rhema_0"
    conn.close()


def test_serialize_embedding_roundtrip():
    blob = serialize_embedding([1.0, 2.0, 3.0])
    assert isinstance(blob, bytes)
    assert len(blob) == 12


def test_async_session_loads_vec_and_queries(tmp_path):
    async def main():
        db = tmp_path / "async.db"
        conn = await get_async_connection(str(db))
        await init_async_db(conn)

        await conn.execute(
            "INSERT INTO chunks (id, source_type, source_file, date, speaker, "
            "topic_type, topic_title, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-03-01_rhema_0", SourceType.SERMON.value, "2026-Sermons.md",
             "2026-03-01", "Ps. Richard", "Rhema", "The Spirit of Might", "note"),
        )
        vec = serialize_embedding([0.5] * 1536)
        await conn.execute(
            "INSERT INTO chunks_embeddings_1536 (chunk_id, embedding) VALUES (?, ?)",
            ("2026-03-01_rhema_0", vec),
        )
        await conn.commit()

        cur = await conn.execute(
            "SELECT chunk_id, distance FROM chunks_embeddings_1536 "
            "WHERE embedding MATCH ? AND k = 5 ORDER BY distance",
            (serialize_embedding([0.5] * 1536),),
        )
        row = await cur.fetchone()
        await cur.close()
        await conn.close()
        return row

    row = asyncio.run(main())
    assert row is not None
    assert row["chunk_id"] == "2026-03-01_rhema_0"