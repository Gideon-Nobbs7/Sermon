"""Run one-time schema migrations for the embedding index.

Drops the legacy single-table vec0 index so init_db can build the
per-dimension tables, then prints next steps. Run once, then re-seed:

    uv run migrate.py
    uv run seed.py
"""

from __future__ import annotations

import logging

from src.app.config import settings
from src.app.db.database import get_connection, init_db, migrate_vec0
from src.app.logging import setup_logging


def main() -> None:
    setup_logging(settings.LOG_LEVEL)
    logger = logging.getLogger("migrate")

    dims = (settings.EMBEDDING_DIMENSIONS, settings.OPENROUTER_EMBEDDING_DIMENSIONS)
    conn = get_connection()
    migrate_vec0(conn, dims)
    init_db(conn, dimensions=dims)
    conn.close()
    logger.info("schema is up to date - run `uv run seed.py` to re-index embeddings")


if __name__ == "__main__":
    main()