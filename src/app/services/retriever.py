from __future__ import annotations

import json
import logging
from typing import List, Optional, Sequence, Tuple

from ..config import settings
from ..db.database import embedding_table, get_async_db, serialize_embedding
from ..errors import AppError
from ..schemas.sermon import Chunk, SourceType
from .embeddings import EmbeddingService

logger = logging.getLogger("app.retriever")


class Retriever:
    """Embed the query and return the top-k matching chunks with metadata.
    """

    def __init__(
        self,
        embed_services: Sequence[Tuple[EmbeddingService, int]],
        db_path: Optional[str] = None,
        default_k: int = 5,
    ):
        self.embed_services = list(embed_services)
        self.db_path = db_path or str(settings.SQLITE_DB_PATH)
        self.default_k = default_k

    async def retrieve(self, query: str, k: Optional[int] = None) -> List[Chunk]:
        k = k or self.default_k
        errors: List[Exception] = []

        for service, dim in self.embed_services:
            try:
                [vector] = await service.aembed([query])
            except Exception as exc:
                logger.warning("embedding provider %s failed: %s", service.model, exc)
                errors.append(exc)
                continue

            table = embedding_table(dim)
            sql = f"""
                SELECT c.id, c.source_type, c.source_file, c.date, c.speaker,
                       c.topic_type, c.topic_title, c.scriptures, c.page, c.text
                FROM {table} e
                JOIN chunks c ON c.id = e.chunk_id
                WHERE e.embedding MATCH ? AND k = ?
                ORDER BY e.distance
            """
            async with get_async_db(self.db_path) as conn:
                cur = await conn.execute(sql, (serialize_embedding(vector), k))
                rows = await cur.fetchall()
                await cur.close()
            return [_row_to_chunk(r) for r in rows]

        first_app_error = next((e for e in errors if isinstance(e, AppError)), None)
        if first_app_error is not None:
            raise first_app_error
        raise AppError(502, "All embedding providers failed.", "embeddings_all_failed")


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