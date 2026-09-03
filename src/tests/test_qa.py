import asyncio

from src.app.db.database import get_connection, init_db
from src.app.schemas.sermon import Chunk, SourceType
from src.app.services.history import ChatHistoryStore
from src.app.services.qa import QAService, _SLOW


class SlowRetriever:
    async def retrieve(self, query, k=None):
        await asyncio.sleep(10)
        return []


class SlowGenerator:
    async def generate(self, chunks, question, history=None):
        await asyncio.sleep(10)
        return "never"


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    async def retrieve(self, query, k=None):
        return self.chunks


class FakeGenerator:
    async def generate(self, chunks, question, history=None):
        return "answer"


def _store(tmp_path):
    db = tmp_path / "qa.db"
    conn = get_connection(str(db))
    init_db(conn)
    conn.close()
    return ChatHistoryStore(db_path=str(db))


def _chunk():
    return Chunk(
        id="c1", source_file="2026-Sermons.md", source_type=SourceType.SERMON,
        date="2026-02-15", speaker="Ps. Richard", topic_title="The Spirit of Might",
        text="note",
    )


def test_timeout_returns_early_message(tmp_path):
    store = _store(tmp_path)
    qa = QAService(SlowRetriever(), SlowGenerator(), store, timeout=0.1)

    result = asyncio.run(qa.answer("chat-1", "q"))

    assert result.answer == _SLOW
    assert result.sources == []
    turns = asyncio.run(store.recent("chat-1"))
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[-1]["content"] == _SLOW


def test_normal_path_returns_answer_and_sources(tmp_path):
    store = _store(tmp_path)
    qa = QAService(FakeRetriever([_chunk()]), FakeGenerator(), store, timeout=5)

    result = asyncio.run(qa.answer("chat-1", "what was taught?"))

    assert result.answer == "answer"
    assert result.sources[0]["speaker"] == "Ps. Richard"
    turns = asyncio.run(store.recent("chat-1"))
    assert turns[-1]["content"] == "answer"