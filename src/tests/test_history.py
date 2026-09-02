import asyncio

import aiosqlite
import pytest

from src.app.db.database import get_connection, init_db
from src.app.services.history import ChatHistoryStore


def _init(db_path):
    conn = get_connection(str(db_path))
    init_db(conn)
    conn.close()


def test_append_and_recent(tmp_path):
    db = tmp_path / "history.db"
    _init(db)

    store = ChatHistoryStore(db_path=str(db), limit=8)
    asyncio.run(store.append("chat-1", "user", "hello"))
    asyncio.run(store.append("chat-1", "assistant", "hi there"))

    turns = asyncio.run(store.recent("chat-1"))
    assert turns == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_history_is_persisted_and_hydrated(tmp_path):
    db = tmp_path / "history.db"
    _init(db)

    store = ChatHistoryStore(db_path=str(db), limit=8)
    asyncio.run(store.append("chat-1", "user", "q1"))
    asyncio.run(store.append("chat-1", "assistant", "a1"))

    fresh = ChatHistoryStore(db_path=str(db), limit=8)
    turns = asyncio.run(fresh.recent("chat-1"))
    assert turns == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]


def test_recent_is_capped_at_limit(tmp_path):
    db = tmp_path / "history.db"
    _init(db)

    store = ChatHistoryStore(db_path=str(db), limit=3)
    for i in range(5):
        asyncio.run(store.append("chat-1", "user", f"q{i}"))

    turns = asyncio.run(store.recent("chat-1"))
    assert [t["content"] for t in turns] == ["q2", "q3", "q4"]


def test_chats_are_isolated(tmp_path):
    db = tmp_path / "history.db"
    _init(db)

    store = ChatHistoryStore(db_path=str(db), limit=8)
    asyncio.run(store.append("chat-1", "user", "one"))
    asyncio.run(store.append("chat-2", "user", "two"))

    assert asyncio.run(store.recent("chat-1"))[0]["content"] == "one"
    assert asyncio.run(store.recent("chat-2"))[0]["content"] == "two"


def test_db_failure_does_not_mutate_memory(tmp_path, monkeypatch):
    db = tmp_path / "history.db"
    _init(db)

    store = ChatHistoryStore(db_path=str(db), limit=8)
    asyncio.run(store.recent("chat-1"))

    class Boom(Exception):
        pass

    async def failing_execute(self, sql, parameters):
        raise Boom("db down")

    monkeypatch.setattr(aiosqlite.Connection, "execute", failing_execute)

    with pytest.raises(Boom):
        asyncio.run(store.append("chat-1", "user", "hello"))

    assert list(store._memory["chat-1"]) == []