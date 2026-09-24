"""Seed/index the corpus from all ingestion sources (idempotent).

New chunks are inserted and really-changed chunks are updated and re-embedded
(whitespace-only differences are ignored). Safe to re-run.

    uv run seed.py                      # uses settings paths
    uv run seed.py --sermon-file 2026-Sermons.md
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import List

from src.app.context import new_request_id, request_scope
from src.app.logging import setup_logging

from src.app.config import settings
from src.app.db.database import get_connection, init_db
from src.app.schemas.sermon import Chunk
from src.app.services.embeddings import OpenAIEmbeddingService
from src.app.services.loaders import load_document
from src.app.services.parser import SermonMarkdownParser
from src.app.workers.watcher import index_chunks

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
        changed, embedded = index_chunks(conn, chunks, build_embed_services())

        total = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        logger.info(
            "collected=%d changed=%d embedded=%d total=%d",
            len(chunks),
            changed,
            embedded,
            total,
        )
        conn.close()


if __name__ == "__main__":
    main()
