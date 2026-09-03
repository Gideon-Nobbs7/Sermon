"""SQLite connection + session management with the sqlite-vec extension."""

import sqlite3
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator, Optional, Sequence, Tuple

import aiosqlite
import sqlite_vec

from ..config import settings

DEFAULT_EMBEDDING_DIMS: Tuple[int, ...] = (1536, 2048)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_file TEXT NOT NULL,
    date        TEXT,
    speaker     TEXT,
    topic_type  TEXT,
    topic_title TEXT,
    scriptures  TEXT,
    page        INTEGER,
    text        TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_file);
CREATE INDEX IF NOT EXISTS idx_chunks_date ON chunks(date);
CREATE INDEX IF NOT EXISTS idx_chunks_speaker ON chunks(speaker);

CREATE TABLE IF NOT EXISTS chat_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_history_chat ON chat_history(chat_id, id);
"""


def embedding_table(dim: int) -> str:
    return f"chunks_embeddings_{dim}"


def _vec0_sql(dimensions: Tuple[int, ...]) -> str:
    return "\n".join(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {embedding_table(d)} USING vec0(\n"
        f"    chunk_id TEXT PRIMARY KEY,\n"
        f"    embedding FLOAT[{d}] distance_metric=cosine\n);"
        for d in dimensions
    )


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or str(settings.SQLITE_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def migrate_vec0(conn: sqlite3.Connection, dimensions: Tuple[int, ...]) -> None:
    """Drop any embedding index not in the current dimension set (one-time)."""
    keep = {embedding_table(d) for d in dimensions}
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name LIKE 'chunks_embeddings%'"
        )
    ]
    for name in tables:
        suffix = name[len("chunks_embeddings_"):]
        is_main = name == "chunks_embeddings" or suffix.isdigit()
        if is_main and name not in keep:
            conn.execute(f"DROP TABLE {name}")
    conn.commit()


def init_db(
    conn: sqlite3.Connection,
    dimensions: Tuple[int, ...] = DEFAULT_EMBEDDING_DIMS,
) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_TABLE_SQL)
    conn.executescript(_vec0_sql(dimensions))
    conn.commit()


@contextmanager
def get_db(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


async def get_async_connection(db_path: Optional[str] = None) -> aiosqlite.Connection:
    path = db_path or str(settings.SQLITE_DB_PATH)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.enable_load_extension(True)
    await conn.load_extension(sqlite_vec.loadable_path())
    await conn.enable_load_extension(False)
    return conn


async def init_async_db(
    conn: aiosqlite.Connection,
    dimensions: Tuple[int, ...] = DEFAULT_EMBEDDING_DIMS,
) -> None:
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.executescript(_TABLE_SQL)
    await conn.executescript(_vec0_sql(dimensions))
    await conn.commit()


@asynccontextmanager
async def get_async_db(db_path: Optional[str] = None) -> AsyncIterator[aiosqlite.Connection]:
    conn = await get_async_connection(db_path)
    try:
        yield conn
    finally:
        await conn.close()


def serialize_embedding(vector: Sequence[float]) -> bytes:
    return sqlite_vec.serialize_float32(list(vector))