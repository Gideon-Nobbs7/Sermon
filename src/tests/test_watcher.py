import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.app.workers.watcher import (
    SermonHandler,
    collect_chunks,
    collect_chunks_for_file,
    index_chunks,
    startup_scan,
)

SERMON_MD = """\
### 8th Feb, 2026 ###
#### Exhortation: Ps. Derrick - The Spirit of Excellence ####
 - The spirit of excellence sets a man above his fellows.
#### Rhema: Ps. Richard - The Need To Keep Your Spirit Sharp ####
 - Many of the crisis believers go through.
"""


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def sermon_file(data_dir):
    p = data_dir / "2026-Sermons.md"
    p.write_text(SERMON_MD)
    return p


@pytest.fixture
def embed_services():
    svc = MagicMock()
    svc.embed.return_value = [[0.1] * 1536, [0.2] * 1536]
    return [(svc, 1536)]


@pytest.fixture
def db_path(tmp_path):
    from src.app.db.database import get_connection, init_db

    path = str(tmp_path / "test.db")
    conn = get_connection(path)
    init_db(conn, dimensions=(1536,))
    conn.close()
    return path


class TestCollectChunksForFile:
    def test_sermon_file(self, sermon_file):
        chunks = collect_chunks_for_file(sermon_file)
        assert len(chunks) == 2
        assert chunks[0].source_type.value == "sermon"
        assert chunks[0].date == "2026-02-08"
        assert chunks[0].speaker == "Ps. Derrick"

    def test_unknown_file_returns_empty(self, tmp_path):
        p = tmp_path / "random.txt"
        p.write_text("hello")
        chunks = collect_chunks_for_file(p)
        assert chunks == []

    def test_nonexistent_file(self, tmp_path):
        p = tmp_path / "does_not_exist.md"
        chunks = collect_chunks_for_file(p)
        assert chunks == []


class TestCollectChunks:
    def test_both_sources(self, data_dir, sermon_file):
        doc = data_dir / "notes.txt"
        doc.write_text("not a supported file")
        chunks = collect_chunks(sermon_file, data_dir)
        assert len(chunks) == 2

    def test_no_sermon_file(self, data_dir):
        missing = data_dir / "2026-Sermons.md"
        chunks = collect_chunks(missing, data_dir)
        assert chunks == []


class TestIndexChunks:
    def test_inserts_new_chunks(self, db_path, embed_services):
        from src.app.db.database import get_connection

        conn = get_connection(db_path)
        chunks = collect_chunks_for_file = [
            MagicMock(
                id="test_1",
                source_type=MagicMock(value="sermon"),
                source_file="test.md",
                date="2026-01-01",
                speaker="Ps. Test",
                topic_type="Rhema",
                topic_title="Test Topic",
                scriptures=["John 3:16"],
                page=None,
                text="Test sermon notes",
            )
        ]
        inserted = index_chunks(conn, chunks, embed_services)
        assert inserted >= 0
        total = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        assert total == 1
        conn.close()

    def test_skips_existing_chunks(self, db_path, embed_services):
        from src.app.db.database import get_connection

        conn = get_connection(db_path)
        chunk = MagicMock(
            id="test_dup",
            source_type=MagicMock(value="sermon"),
            source_file="test.md",
            date="2026-01-01",
            speaker="Ps. Test",
            topic_type="Rhema",
            topic_title="Test Topic",
            scriptures=["John 3:16"],
            page=None,
            text="Test sermon notes",
        )
        index_chunks(conn, [chunk], embed_services)
        inserted = index_chunks(conn, [chunk], embed_services)
        assert inserted == 0
        total = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        assert total == 1
        conn.close()


class TestSermonHandler:
    def test_debounce_cancels_previous(self, embed_services, db_path):
        handler = SermonHandler(
            embed_services, db_path=db_path, debounce_seconds=0.1
        )
        with patch.object(handler, "_process") as mock_process:
            handler._debounce("/fake/path1.txt")
            handler._debounce("/fake/path1.txt")
            time.sleep(0.3)
            assert mock_process.call_count == 1

    def test_different_files_debounce_separately(self, embed_services, db_path):
        handler = SermonHandler(
            embed_services, db_path=db_path, debounce_seconds=0.1
        )
        with patch.object(handler, "_process") as mock_process:
            handler._debounce("/fake/path1.txt")
            handler._debounce("/fake/path2.txt")
            time.sleep(0.3)
            assert mock_process.call_count == 2

    def test_on_created_triggers_debounce(self, embed_services, db_path):
        handler = SermonHandler(
            embed_services, db_path=db_path, debounce_seconds=0.1
        )
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/fake/file.txt"
        with patch.object(handler, "_debounce") as mock_debounce:
            handler.on_created(event)
            mock_debounce.assert_called_once_with("/fake/file.txt")

    def test_on_directory_ignored(self, embed_services, db_path):
        handler = SermonHandler(
            embed_services, db_path=db_path, debounce_seconds=0.1
        )
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/fake/dir"
        with patch.object(handler, "_debounce") as mock_debounce:
            handler.on_created(event)
            mock_debounce.assert_not_called()


class TestStartupScan:
    def test_startup_scan_inserts_chunks(
        self, data_dir, sermon_file, embed_services, db_path
    ):
        from src.app.config import settings

        with patch.object(settings, "SERMON_FILE_PATH", sermon_file), patch.object(
            settings, "DATA_DIR", data_dir
        ), patch.object(settings, "SQLITE_DB_PATH", Path(db_path)):
            startup_scan(embed_services, db_path)

        from src.app.db.database import get_connection

        conn = get_connection(db_path)
        total = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        assert total == 2
        conn.close()
