"""
Watcher worker — monitors the data folder for new or changed files and triggers embedding.

Runs as a standalone service. On startup, it performs a full scan in a background
thread so it never blocks user's requests. Then watches for file changes with debouncing.

Usage:
    python -m src.app.workers.watcher
"""

from __future__ import annotations

import json
import logging
import re
import signal
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ..config import settings
from ..context import new_request_id, request_scope
from ..db.database import get_connection, init_db
from ..logging import setup_logging
from ..schemas.sermon import Chunk
from ..services.embeddings import OpenAIEmbeddingService
from ..services.loaders import load_document
from ..services.parser import SermonMarkdownParser

logger = logging.getLogger("watcher")

_EXTENSIONS = {".pdf", ".docx", ".doc"}

# Files that must never trigger the embedding pipeline. The SQLite database
# lives inside the watched DATA_DIR so its write-ahead-log sidecars would
# otherwise schedule pointless and self-reinforcing parse attempts.
_IGNORED_SUFFIXES = frozenset(
    {".db", ".db-wal", ".db-shm", ".db-journal", ".tmp", ".swp", ".swx"}
)
_IGNORED_EXACT = frozenset({"thumbs.db", ".ds_store"})


def should_ignore(path: str | Path) -> bool:
    """True when a changed path is a DB artifact or temp file, not content."""
    name = Path(path).name
    lowered = name.lower()
    if lowered in _IGNORED_EXACT or lowered.endswith("~"):
        return True
    suffixes = "".join(Path(lowered).suffixes[-2:])
    if suffixes in _IGNORED_SUFFIXES:
        return True
    return Path(lowered).suffix in _IGNORED_SUFFIXES


def _normalize(text: Optional[str]) -> str:
    """Collapse whitespace so a stray space/tab never counts as an update."""
    return re.sub(r"\s+", " ", (text or "").strip())


def build_embed_services() -> List[tuple]:
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
        if path.suffix.lower() in _EXTENSIONS:
            chunks.extend(load_document(str(path)))

    return chunks


def collect_chunks_for_file(file_path: Path) -> List[Chunk]:
    """Parse a single file into chunks."""
    if file_path.suffix.lower() in _EXTENSIONS:
        return load_document(str(file_path))

    if file_path.name == settings.SERMON_FILE_PATH.name:
        parser = SermonMarkdownParser()
        sermons = parser.parse_file(str(file_path))
        for c in sermons:
            c.source_file = file_path.name
        return sermons

    return []


def _chunk_row(c: Chunk) -> tuple:
    import json

    return (
        c.id,
        c.source_type.value,
        c.source_file,
        c.date,
        c.speaker,
        c.topic_type,
        c.topic_title,
        json.dumps(c.scriptures) if c.scriptures else None,
        c.page,
        c.text,
    )


def _row_changed(row, c: Chunk) -> bool:
    """True only when content really changed; stray spaces/tabs don't count."""
    import json

    try:
        stored_scriptures = json.loads(row["scriptures"]) if row["scriptures"] else []
    except (TypeError, ValueError):
        stored_scriptures = []
    return (
        (row["source_file"] or "") != (c.source_file or "")
        or (row["date"] or "") != (c.date or "")
        or _normalize(row["speaker"]) != _normalize(c.speaker)
        or _normalize(row["topic_type"]) != _normalize(c.topic_type)
        or _normalize(row["topic_title"]) != _normalize(c.topic_title)
        or (stored_scriptures or []) != (list(c.scriptures) if c.scriptures else [])
        or (row["page"] if row["page"] is not None else None) != c.page
        or _normalize(row["text"]) != _normalize(c.text)
    )


def index_chunks(
    conn, chunks: List[Chunk], embed_services: List[tuple]
) -> Tuple[int, int]:
    """
    Insert new chunks, update really-changed ones. Returns (changed, embedded).
    """
    # Collapse intra-batch duplicates (parser ids repeat per date block).
    by_id: Dict[str, Chunk] = {}
    for c in chunks:
        by_id[c.id] = c
    chunks = list(by_id.values())

    existing = {
        r["id"]: r
        for r in conn.execute(
            "SELECT id, source_file, date, speaker, topic_type, topic_title, "
            "scriptures, page, text FROM chunks"
        )
    }
    to_insert = [c for c in chunks if c.id not in existing]
    to_update = [c for c in chunks if c.id in existing and _row_changed(existing[c.id], c)]

    if to_insert:
        conn.executemany(
            "INSERT OR IGNORE INTO chunks (id, source_type, source_file, date, speaker, "
            "topic_type, topic_title, scriptures, page, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [_chunk_row(c) for c in to_insert],
        )

    if to_update:
        conn.executemany(
            "UPDATE chunks SET source_type = ?, source_file = ?, date = ?, speaker = ?, "
            "topic_type = ?, topic_title = ?, scriptures = ?, page = ?, text = ? "
            "WHERE id = ?",
            [
                (
                    c.source_type.value,
                    c.source_file,
                    c.date,
                    c.speaker,
                    c.topic_type,
                    c.topic_title,
                    json.dumps(c.scriptures) if c.scriptures else None,
                    c.page,
                    c.text,
                    c.id,
                )
                for c in to_update
            ],
        )

    changed = to_insert + to_update

    from ..db.database import embedding_table, serialize_embedding

    # Re-embed new and updated chunks. Drop stale vectors first.
    updated_ids = {c.id for c in to_update}
    if updated_ids:
        for _service, dim in embed_services:
            table = embedding_table(dim)
            conn.executemany(
                f"DELETE FROM {table} WHERE chunk_id = ?",
                [(cid,) for cid in updated_ids],
            )

    indexed = 0
    for service, dim in embed_services:
        table = embedding_table(dim)
        embedded = {
            r["chunk_id"] for r in conn.execute(f"SELECT chunk_id FROM {table}")
        }
        missing = [c for c in chunks if c.id not in embedded]
        if not missing:
            continue
        try:
            vectors = service.embed([c.text for c in missing])
        except Exception as exc:
            logger.warning(
                "embedding provider %s failed during watch "
                "(retries exhausted, falling back): %s",
                service.model,
                exc,
            )
            continue
        conn.executemany(
            f"INSERT OR IGNORE INTO {table} (chunk_id, embedding) VALUES (?, ?)",
            [
                (c.id, serialize_embedding(v))
                for c, v in zip(missing, vectors)
            ],
        )
        indexed += len(missing)
    conn.commit()
    return len(changed), indexed


class SermonHandler(FileSystemEventHandler):
    """Handles file system events with debouncing."""

    def __init__(
        self,
        embed_services: List[tuple],
        db_path: Optional[str] = None,
        debounce_seconds: float = 2.0,
    ):
        super().__init__()
        self.embed_services = embed_services
        self.db_path = db_path or str(settings.SQLITE_DB_PATH)
        self.debounce_seconds = debounce_seconds
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        self._debounce(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._debounce(event.src_path)

    def _debounce(self, path: str):
        if should_ignore(path):
            logger.debug("ignoring changed file: %s", Path(path).name)
            return
        with self._lock:
            if path in self._timers:
                self._timers[path].cancel()
            timer = threading.Timer(
                self.debounce_seconds, self._process, args=[path]
            )
            self._timers[path] = timer
            timer.start()

    def _process(self, path: str):
        file_path = Path(path)
        if should_ignore(path):
            logger.debug("ignoring changed file: %s", file_path.name)
            return
        if not file_path.is_file():
            return

        with self._lock:
            self._timers.pop(path, None)

        logger.info("processing changed file: %s", file_path.name)
        with request_scope(request_id=new_request_id(), operation="watcher"):
            try:
                chunks = collect_chunks_for_file(file_path)
                if not chunks:
                    logger.debug("no chunks extracted from %s", file_path.name)
                    return
                conn = get_connection(self.db_path)
                changed, embedded = index_chunks(conn, chunks, self.embed_services)
                conn.close()
                logger.info(
                    "indexed %s: chunks=%d changed=%d embedded=%d",
                    file_path.name,
                    len(chunks),
                    changed,
                    embedded,
                )
            except Exception:
                logger.exception("failed to process %s", file_path.name)


def startup_scan(
    embed_services: List[tuple],
    db_path: Optional[str] = None,
) -> None:
    """Full corpus scan — runs in a background thread on startup."""
    path = db_path or str(settings.SQLITE_DB_PATH)
    logger.info("starting startup scan")
    with request_scope(request_id=new_request_id(), operation="startup_scan"):
        try:
            sermon_file = settings.SERMON_FILE_PATH
            data_dir = settings.DATA_DIR
            chunks = collect_chunks(sermon_file, data_dir)
            conn = get_connection(path)
            changed, embedded = index_chunks(conn, chunks, embed_services)
            total = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
            conn.close()
            logger.info(
                "startup scan complete: collected=%d changed=%d embedded=%d total=%d",
                len(chunks),
                changed,
                embedded,
                total,
            )
        except Exception:
            logger.exception("startup scan failed")


def run(
    embed_services: Optional[List[tuple]] = None,
    db_path: Optional[str] = None,
) -> None:
    """Run the watcher worker. Blocks until SIGTERM/SIGINT."""
    setup_logging(settings.LOG_LEVEL)

    if embed_services is None:
        embed_services = build_embed_services()

    path = db_path or str(settings.SQLITE_DB_PATH)

    conn = get_connection(path)
    init_db(
        conn,
        dimensions=(
            settings.EMBEDDING_DIMENSIONS,
            settings.OPENROUTER_EMBEDDING_DIMENSIONS,
        ),
    )
    conn.close()

    handler = SermonHandler(
        embed_services,
        db_path=path,
        debounce_seconds=settings.WATCHER_DEBOUNCE_SECONDS,
    )

    observer = Observer()
    observer.schedule(handler, str(settings.DATA_DIR), recursive=True)
    observer.start()
    logger.info(
        "watcher started, monitoring %s (poll_interval=%.1fs)",
        settings.DATA_DIR,
        settings.WATCHER_POLL_INTERVAL,
    )

    scan_thread = threading.Thread(
        target=startup_scan,
        args=(embed_services, path),
        daemon=True,
    )
    scan_thread.start()

    shutdown = threading.Event()

    def _shutdown(signum, _frame):
        logger.info("received signal %s, shutting down", signum)
        shutdown.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        shutdown.wait()
    finally:
        observer.stop()
        observer.join()
        logger.info("watcher stopped")


if __name__ == "__main__":
    run()
