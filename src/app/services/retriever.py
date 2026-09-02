from __future__ import annotations

import json
from typing import List, Optional

from ..config import settings
from ..db.database import get_async_db, serialize_embedding
from ..schemas.sermon import Chunk, SourceType
from .embeddings import EmbeddingService


class Retriever:
    """Embed the query and return the top-k matching chunks with metadata."""

    def __init__(
        self,
        embed_service: EmbeddingService,
        db_path: Optional[str] = None,
        default_k: int = 5,
    ):
        self.embed_service = embed_service
        self.db_path = db_path or str(settings.SQLITE_DB_PATH)
        self.default_k = default_k

    async def retrieve(self, query: str, k: Optional[int] = None) -> List[Chunk]:
        k = k or self.default_k
        [vector] = await self.embed_service.aembed([query])

        sql = """
            SELECT c.id, c.source_type, c.source_file, c.date, c.speaker,
                   c.topic_type, c.topic_title, c.scriptures, c.page, c.text
            FROM chunks_embeddings e
            JOIN chunks c ON c.id = e.chunk_id
            WHERE e.embedding MATCH ? AND k = ?
            ORDER BY e.distance
        """

        async with get_async_db(self.db_path) as conn:
            cur = await conn.execute(sql, (serialize_embedding(vector), k))
            rows = await cur.fetchall()
            await cur.close()

        return [_row_to_chunk(r) for r in rows]


def _row_to_chunk(row) -> Chunk:
    return Chunk(
        id=row["id"],
        source_type=SourceType(row["source_type"]),
        source_file=row["source_file"],
        date=row["date"],
        speaker=row["speaker"],
        topic_type=row["topic_type"],
        topic_title=row["topic_title"],
        scriptures=json.loads(row["scriptures"]) if row["scriptures"] else [],
        page=row["page"],
        text=row["text"],
    )