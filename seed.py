"""Seed/index the corpus from all ingestion sources (idempotent).

Only chunks whose id is not already in `chunks` are embedded and inserted.

    uv run seed.py                      # uses settings paths
    uv run seed.py --sermon-file 2026-Sermons.md
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import List

from src.app.context import new_request_id, request_scope
from src.app.logging import setup_logging

from src.app.config import settings
from src.app.db.database import (
    embedding_table,
    get_connection,
    init_db,
    serialize_embedding,
)
from src.app.schemas.sermon import Chunk
from src.app.services.embeddings import OpenAIEmbeddingService
from src.app.services.loaders import load_document
from src.app.services.parser import SermonMarkdownParser

logger = logging.getLogger("seed")


def build_embed_services() -> List:
    return [
        (
            OpenAIEmbeddingService(
                api_key=settings.OPENAI_API_KEY,
                model=settings.EMBEDDING_MODEL,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            ),
            settings.EMBEDDING_DIMENSIONS,
        ),
        (
            OpenAIEmbeddingService(
                api_key=settings.OPENROUTER_API_KEY,
                model=settings.OPENROUTER_EMBEDDING_MODEL,
                dimensions=settings.OPENROUTER_EMBEDDING_DIMENSIONS,
                url=f"{settings.OPENROUTER_BASE_URL}/embeddings",
                key_env="OPENROUTER_API_KEY",
            ),
            settings.OPENROUTER_EMBEDDING_DIMENSIONS,
        ),
    ]


def collect_chunks(sermon_file: Path, data_dir: Path) -> List[Chunk]:
    chunks: List[Chunk] = []
    parser = SermonMarkdownParser()

    if sermon_file.is_file():
        sermons = parser.parse_file(str(sermon_file))
        for c in sermons:
            c.source_file = sermon_file.name
        chunks.extend(sermons)

    for path in sorted(data_dir.iterdir()):
        if path.suffix.lower() in (".pdf", ".docx", ".doc"):
            chunks.extend(load_document(str(path)))

    return chunks


def index_chunks(conn, chunks: List[Chunk], embed_services: List) -> int:
    existing = {r["id"] for r in conn.execute("SELECT id FROM chunks")}
    new = [c for c in chunks if c.id not in existing]
    if new:
        conn.executemany(
            "INSERT INTO chunks (id, source_type, source_file, date, speaker, "
            "topic_type, topic_title, scriptures, page, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    c.id, c.source_type.value, c.source_file, c.date, c.speaker,
                    c.topic_type, c.topic_title,
                    json.dumps(c.scriptures) if c.scriptures else None,
                    c.page, c.text,
                )
                for c in new
            ],
        )

    indexed = 0
    for service, dim in embed_services:
        table = embedding_table(dim)
        embedded = {
            r["chunk_id"]
            for r in conn.execute(f"SELECT chunk_id FROM {table}")
        }
        missing = [c for c in chunks if c.id not in embedded]
        if not missing:
            continue
        try:
            vectors = service.embed([c.text for c in missing])
        except Exception as exc:
            logger.warning("embedding provider %s failed during seed: %s", service.model, exc)
            continue
        conn.executemany(
            f"INSERT INTO {table} (chunk_id, embedding) VALUES (?, ?)",
            [(c.id, serialize_embedding(v)) for c, v in zip(missing, vectors)],
        )
        indexed += len(missing)
    conn.commit()
    return indexed


def main() -> None:
    setup_logging(settings.LOG_LEVEL)
    parser = argparse.ArgumentParser(description="Seed the sermon corpus")
    parser.add_argument("--sermon-file", default=None, help="path to the sermon markdown")
    parser.add_argument("--db", default=None, help="path to the SQLite database")
    args = parser.parse_args()

    sermon_file = Path(args.sermon_file) if args.sermon_file else settings.SERMON_FILE_PATH
    data_dir = settings.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    with request_scope(request_id=new_request_id(), operation="seed"):
        logger.info("collecting chunks from %s and %s", sermon_file, data_dir)
        chunks = collect_chunks(sermon_file, data_dir)

        conn = get_connection(args.db)
        init_db(
            conn,
            dimensions=(
                settings.EMBEDDING_DIMENSIONS,
                settings.OPENROUTER_EMBEDDING_DIMENSIONS,
            ),
        )
        inserted = index_chunks(conn, chunks, build_embed_services())

        total = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        logger.info("collected=%d new=%d total=%d", len(chunks), inserted, total)
        conn.close()


if __name__ == "__main__":
    main()
