import json

import httpx
import pytest

from src.app.services import bible as bible_module
from src.app.services.bible import (
    BibleVerseService,
    display_ref,
    parse_reference,
    preload_bible_bundle,
)


@pytest.fixture
def fresh_bundle_cache():
    saved = dict(bible_module._BUNDLE_CACHE)
    bible_module._BUNDLE_CACHE.clear()
    try:
        yield
    finally:
        bible_module._BUNDLE_CACHE.clear()
        bible_module._BUNDLE_CACHE.update(saved)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Ps 110:3", ("Psalms", 110, 3, 3)),
        ("Psalm 133:3", ("Psalms", 133, 3, 3)),
        ("Ps. 23:1", ("Psalms", 23, 1, 1)),
        ("John 3:16", ("John", 3, 16, 16)),
        ("1 Cor 13:4", ("1 Corinthians", 13, 4, 4)),
        ("1 John 1:9", ("1 John", 1, 9, 9)),
        ("2 Tim 2:15", ("2 Timothy", 2, 15, 15)),
        ("Song 2:1", ("Song of Solomon", 2, 1, 1)),
        ("John 3:16-18", ("John", 3, 16, 18)),
        ("Gen 1:1", ("Genesis", 1, 1, 1)),
        ("Rev 22:21", ("Revelation", 22, 21, 21)),
    ],
)
def test_parse_reference_valid(raw, expected):
    assert parse_reference(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "hello",
        "Gen",
        "3:16",
        "",
        "John 0:1",
        "John 1:0",
        "John 1:5-2",
        "Narnia 1:1",
        "John 3",
    ],
)
def test_parse_reference_invalid(raw):
    assert parse_reference(raw) is None


def test_parse_reference_range_clamped_to_cap():
    assert parse_reference("John 3:16-99") == ("John", 3, 16, 19)


def test_display_ref():
    assert display_ref("John", 3, 16, 16) == "John 3:16"
    assert display_ref("John", 3, 16, 18) == "John 3:16-18"


def _bundle_file(tmp_path):
    payload = {
        "meta": {"translation": "KJV"},
        "books": {
            "Psalms": {"133": {"3": "there the LORD commanded the blessing"}},
            "John": {"3": {"16": "God so loved the world"}},
        },
    }
    path = tmp_path / "kjv.json"
    path.write_text(json.dumps(payload))
    return path


def _service(tmp_path, **overrides):
    db = str(tmp_path / "test.db")
    from src.app.db.database import get_connection, init_db

    conn = get_connection(db)
    init_db(conn)
    conn.close()
    return BibleVerseService(
        json_path=_bundle_file(tmp_path), db_path=db, **overrides
    )


def test_get_from_bundle(tmp_path):
    svc = _service(tmp_path)
    assert svc.get("Ps 133:3") == (
        "Psalms 133:3",
        "(Psalms 133:3) there the LORD commanded the blessing",
    )


def test_cache_serves_after_bundle_gone(tmp_path):
    svc = _service(tmp_path)
    assert svc.get("John 3:16") is not None

    offline = BibleVerseService(
        json_path=tmp_path / "missing.json", db_path=str(tmp_path / "test.db")
    )
    assert offline.get("John 3:16") == (
        "John 3:16",
        "(John 3:16) God so loved the world",
    )


def test_api_fallback_when_bundle_missing_verse(tmp_path, monkeypatch):
    svc = _service(tmp_path)

    def fake_get(url, timeout):
        assert "Micah" in url
        resp = httpx.Response(
            200,
            json={
                "verses": [
                    {"book_name": "Micah", "chapter": 5, "verse": 7, "text": "as a dew"}
                ]
            },
            request=httpx.Request("GET", url),
        )
        return resp

    monkeypatch.setattr(httpx, "get", fake_get)
    assert svc.get("Micah 5:7") == ("Micah 5:7", "(Micah 5:7) as a dew")


def test_unresolvable_ref_returns_none(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    monkeypatch.setattr(
        httpx, "get", lambda url, timeout: (_ for _ in ()).throw(httpx.ConnectError("down"))
    )
    assert svc.get("Gen 200:1") is None


def test_api_error_body_returns_none(tmp_path, monkeypatch):
    svc = _service(tmp_path)

    def fake_get(url, timeout):
        return httpx.Response(
            200,
            json={"error": "not found"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    assert svc.get("Micah 5:7") is None


def test_get_many_dedupes_and_limits(tmp_path):
    svc = _service(tmp_path)
    out = svc.get_many(["Ps 133:3", "Psalms 133:3", "John 3:16"], limit=1)
    assert len(out) == 1
    assert out[0][0] == "Psalms 133:3"


def test_bundle_parsed_once_and_shared(tmp_path, fresh_bundle_cache, monkeypatch):
    parses = []
    real_load = json.load

    def counting_load(fp):
        parses.append(1)
        return real_load(fp)

    monkeypatch.setattr(json, "load", counting_load)
    first = _service(tmp_path)
    second = _service(tmp_path)

    assert first._load_bundle() is second._load_bundle()
    assert len(parses) == 1


def test_missing_bundle_warns_once_and_caches_none(tmp_path, fresh_bundle_cache, caplog):
    db = str(tmp_path / "test.db")
    one = BibleVerseService(json_path=tmp_path / "missing.json", db_path=db)
    two = BibleVerseService(json_path=tmp_path / "missing.json", db_path=db)

    with caplog.at_level("WARNING", logger="app.bible"):
        assert one._load_bundle() is None
        assert two._load_bundle() is None

    assert len([r for r in caplog.records if "not found" in r.message]) == 1


def test_preload_warms_cache_and_never_raises(tmp_path, fresh_bundle_cache):
    path = _bundle_file(tmp_path)
    preload_bible_bundle(path)
    assert str(path) in bible_module._BUNDLE_CACHE

    preload_bible_bundle(tmp_path / "does-not-exist.json")

    BibleVerseService(json_path=path, db_path=str(tmp_path / "t.db")).warm()
    assert str(path) in bible_module._BUNDLE_CACHE
