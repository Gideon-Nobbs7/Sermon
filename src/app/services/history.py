from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional

from ..config import settings
from ..db.database import get_async_db


class ChatHistoryStore:
    """
    Per-chat conversation history.
    Recent turns are kept in memory and written through
    to SQLite so history survives restarts.
    """

    def __init__(self, db_path: Optional[str] = None, limit: int = 8):
        self.db_path = db_path or str(settings.SQLITE_DB_PATH)
        self.limit = limit
        self._memory: Dict[str, deque] = {}

    async def _load(self, chat_id: str) -> List[dict]:
        async with get_async_db(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT role, content FROM chat_history "
                "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, self.limit),
            )
            rows = await cur.fetchall()
            await cur.close()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def _deque(self, chat_id: str) -> deque:
        if chat_id not in self._memory:
            self._memory[chat_id] = deque(await self._load(chat_id), maxlen=self.limit)
        return self._memory[chat_id]

    async def append(self, chat_id: str, role: str, content: str) -> None:
        dq = await self._deque(chat_id)
        async with get_async_db(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO chat_history (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content),
            )
            await conn.commit()
        dq.append({"role": role, "content": content})

    async def recent(self, chat_id: str) -> List[dict]:
        return list(await self._deque(chat_id))

    def clear_memory(self) -> None:
        self._memory.clear()