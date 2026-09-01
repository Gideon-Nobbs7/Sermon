"""SQLite connection + session management with the sqlite-vec extension."""

import sqlite3
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator, Optional, Sequence

import aiosqlite
import sqlite_vec

from ..config import settings

_SCHEMA = """
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
CREATE INDEX IF NOT EXISTS idx_chunks_date    ON chunks(date);
CREATE INDEX IF NOT EXISTS idx_chunks_speaker ON chunks(speaker);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_embeddings USING vec0(
    chunk_id  TEXT PRIMARY KEY,
    embedding FLOAT[{dim}] distance_metric=cosine
);
"""


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or str(settings.sqlite_db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db(conn: sqlite3.Connection, dimensions: int = 1536) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA.format(dim=dimensions))
    conn.commit()


@contextmanager
def get_db(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


async def get_async_connection(db_path: Optional[str] = None) -> aiosqlite.Connection:
    path = db_path or str(settings.sqlite_db_path)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.enable_load_extension(True)
    await conn.load_extension(sqlite_vec.loadable_path())
    await conn.enable_load_extension(False)
    return conn


async def init_async_db(conn: aiosqlite.Connection, dimensions: int = 1536) -> None:
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.executescript(_SCHEMA.format(dim=dimensions))
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
