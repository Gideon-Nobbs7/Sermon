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
    def __init__(self):
        self.seen_verses = None

    async def generate(self, chunks, question, history=None, verses=None):
        self.seen_verses = verses
        return "answer"


class FakeBible:
    def __init__(self, verses=None, explode=False):
        self.verses = verses or []
        self.explode = explode

    async def aget_many(self, refs, limit=8):
        if self.explode:
            raise RuntimeError("verse backend down")
        return self.verses


def _store(tmp_path):
    db = tmp_path / "qa.db"
    conn = get_connection(str(db))
    init_db(conn)
    conn.close()
    return ChatHistoryStore(db_path=str(db))


def _chunk(scriptures=None):
    return Chunk(
        id="c1", source_file="2026-Sermons.md", source_type=SourceType.SERMON,
        date="2026-02-15", speaker="Ps. Richard", topic_title="The Spirit of Might",
        scriptures=scriptures or [], text="note",
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


def test_verses_resolve_and_reach_generator(tmp_path):
    store = _store(tmp_path)
    gen = FakeGenerator()
    bible = FakeBible(verses=[("Psalms 133:3", "(Psalms 133:3) commanded the blessing")])
    qa = QAService(
        FakeRetriever([_chunk(scriptures=["Ps 133:3"])]), gen, store,
        timeout=5, bible=bible,
    )

    result = asyncio.run(qa.answer("chat-1", "what blessing?"))

    assert result.answer == "answer"
    assert gen.seen_verses == [("Psalms 133:3", "(Psalms 133:3) commanded the blessing")]


def test_verse_backend_failure_still_answers(tmp_path):
    store = _store(tmp_path)
    gen = FakeGenerator()
    qa = QAService(
        FakeRetriever([_chunk(scriptures=["Ps 133:3"])]), gen, store,
        timeout=5, bible=FakeBible(explode=True),
    )

    result = asyncio.run(qa.answer("chat-1", "what blessing?"))

    assert result.answer == "answer"
    assert gen.seen_verses == []