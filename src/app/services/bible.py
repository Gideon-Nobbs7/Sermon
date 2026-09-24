"""
Bible verse lookup for grounded answers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from ..config import settings

logger = logging.getLogger("app.bible")

# Eager load the parsed bundle once and shared across services and workers
_BUNDLE_CACHE: Dict[str, Optional[dict]] = {}


def load_bundle(json_path: Path | str) -> Optional[dict]:
    key = str(json_path)
    if key not in _BUNDLE_CACHE:
        try:
            with open(json_path, encoding="utf-8") as f:
                payload = json.load(f)
            _BUNDLE_CACHE[key] = payload.get("books", payload)
            logger.info("loaded bible bundle: %s", json_path)
        except FileNotFoundError:
            logger.warning(
                "bible bundle not found at %s - using live API only", json_path
            )
            _BUNDLE_CACHE[key] = None
        except (OSError, ValueError) as exc:
            logger.warning(
                "bible bundle at %s unreadable (%s) - using live API only",
                json_path,
                exc,
            )
            _BUNDLE_CACHE[key] = None
    return _BUNDLE_CACHE[key]


def preload_bible_bundle(json_path: Path | str | None = None) -> None:
    try:
        load_bundle(json_path or settings.BIBLE_JSON_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("bible bundle preload failed: %s", exc)

BOOK_NAMES = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John",
    "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians",
    "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
]

# Normalized alias (lowercase, no spaces/dots) -> full book name.
_ALIASES: Dict[str, str] = {}
for _name in BOOK_NAMES:
    _ALIASES[re.sub(r"[\s.]+", "", _name).lower()] = _name
_ALIASES.update(
    {
        "gen": "Genesis",
        "ex": "Exodus",
        "exod": "Exodus",
        "lev": "Leviticus",
        "num": "Numbers",
        "deut": "Deuteronomy",
        "josh": "Joshua",
        "judg": "Judges",
        "jdg": "Judges",
        "1sam": "1 Samuel",
        "2sam": "2 Samuel",
        "1ki": "1 Kings",
        "2ki": "2 Kings",
        "1kings": "1 Kings",
        "2kings": "2 Kings",
        "1chr": "1 Chronicles",
        "2chr": "2 Chronicles",
        "1chron": "1 Chronicles",
        "2chron": "2 Chronicles",
        "ezr": "Ezra",
        "neh": "Nehemiah",
        "esth": "Esther",
        "ps": "Psalms",
        "psa": "Psalms",
        "psalm": "Psalms",
        "prov": "Proverbs",
        "pro": "Proverbs",
        "eccl": "Ecclesiastes",
        "ecc": "Ecclesiastes",
        "song": "Song of Solomon",
        "sos": "Song of Solomon",
        "isa": "Isaiah",
        "is": "Isaiah",
        "jer": "Jeremiah",
        "lam": "Lamentations",
        "ezek": "Ezekiel",
        "eze": "Ezekiel",
        "dan": "Daniel",
        "hos": "Hosea",
        "am": "Amos",
        "obad": "Obadiah",
        "jon": "Jonah",
        "mic": "Micah",
        "nah": "Nahum",
        "hab": "Habakkuk",
        "zeph": "Zephaniah",
        "hag": "Haggai",
        "zech": "Zechariah",
        "zec": "Zechariah",
        "mal": "Malachi",
        "matt": "Matthew",
        "mat": "Matthew",
        "matth": "Matthew",
        "mk": "Mark",
        "lk": "Luke",
        "luk": "Luke",
        "jn": "John",
        "joh": "John",
        "rom": "Romans",
        "ro": "Romans",
        "1cor": "1 Corinthians",
        "2cor": "2 Corinthians",
        "gal": "Galatians",
        "eph": "Ephesians",
        "phil": "Philippians",
        "phili": "Philippians",
        "col": "Colossians",
        "1thess": "1 Thessalonians",
        "2thess": "2 Thessalonians",
        "1tim": "1 Timothy",
        "2tim": "2 Timothy",
        "tit": "Titus",
        "philem": "Philemon",
        "phm": "Philemon",
        "heb": "Hebrews",
        "jam": "James",
        "jas": "James",
        "1pet": "1 Peter",
        "2pet": "2 Peter",
        "1jn": "1 John",
        "2jn": "2 John",
        "3jn": "3 John",
        "jud": "Jude",
        "rev": "Revelation",
    }
)

_REF_RE = re.compile(r"^(.+?)\s+(\d+)\s*:\s*(\d+)(?:\s*[-\u2013\u2014]\s*(\d+))?$")


def parse_reference(ref: str, max_verses: int = 4) -> Optional[Tuple[str, int, int, int]]:
    """
    Normalize "Ps 110:3" -> ("Psalms", 110, 3, 3). None when unparseable.

    Ranges are clamped to `max_verses` verses starting from the first verse.
    """
    if not ref or not isinstance(ref, str):
        return None
    match = _REF_RE.match(ref.strip())
    if not match:
        return None
    book_raw, chapter, start, end = match.groups()
    key = re.sub(r"[\s.]+", "", book_raw).lower()
    book = _ALIASES.get(key)
    if book is None:
        return None
    chapter_no = int(chapter)
    start_no = int(start)
    end_no = int(end) if end else start_no
    if chapter_no < 1 or start_no < 1 or end_no < start_no:
        return None
    if end_no - start_no + 1 > max_verses:
        end_no = start_no + max_verses - 1
    return book, chapter_no, start_no, end_no


def display_ref(book: str, chapter: int, start: int, end: int) -> str:
    if end == start:
        return f"{book} {chapter}:{start}"
    return f"{book} {chapter}:{start}-{end}"


class BibleVerseService:
    """Resolve scripture refs to KJV text with a persistent cache."""

    def __init__(
        self,
        json_path: Optional[Path] = None,
        api_url: Optional[str] = None,
        translation: Optional[str] = None,
        timeout: Optional[float] = None,
        db_path: Optional[str] = None,
        max_verses_per_ref: Optional[int] = None,
    ):
        self.json_path = Path(json_path) if json_path else settings.BIBLE_JSON_PATH
        self.api_url = (api_url or settings.BIBLE_API_URL).rstrip("/")
        self.translation = translation or settings.BIBLE_TRANSLATION
        self.timeout = timeout if timeout is not None else settings.BIBLE_TIMEOUT_SECONDS
        self.db_path = db_path or str(settings.SQLITE_DB_PATH)
        self.max_verses_per_ref = max_verses_per_ref or settings.BIBLE_MAX_VERSES_PER_REF

    def _load_bundle(self) -> Optional[dict]:
        return load_bundle(self.json_path)

    def warm(self) -> None:
        self._load_bundle()

    def _from_bundle(self, book: str, chapter: int, start: int, end: int) -> Optional[str]:
        bundle = self._load_bundle()
        if not bundle:
            return None
        try:
            verses = bundle[book][str(chapter)]
            texts = [verses[str(v)].strip() for v in range(start, end + 1) if str(v) in verses]
        except (KeyError, TypeError):
            return None
        if len(texts) != end - start + 1:
            return None
        return " ".join(f"({book} {chapter}:{v}) {t}" for v, t in zip(range(start, end + 1), texts))

    def _from_api(self, book: str, chapter: int, start: int, end: int) -> Optional[str]:
        ref = f"{book} {chapter}:{start}" if start == end else f"{book} {chapter}:{start}-{end}"
        url = f"{self.api_url}/{quote(ref)}?translation={quote(self.translation.lower())}"
        try:
            resp = httpx.get(url, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.warning("bible API lookup failed for %s: %s", ref, exc)
            return None
        if payload.get("error"):
            logger.debug("bible API reported no text for %s", ref)
            return None
        items = payload.get("verses") or []
        texts = [
            re.sub(r"\s+", " ", str(item.get("text", "")).strip())
            for item in items
            if str(item.get("text", "")).strip()
        ]
        if not texts:
            return None
        parts = []
        for item, text in zip(items, texts):
            parts.append(f"({item.get('book_name', book)} {item.get('chapter', chapter)}:{item.get('verse', start)}) {text}")
        return " ".join(parts)

    def _cache_get(self, ref: str) -> Optional[str]:
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT text FROM bible_verses WHERE ref = ?", (ref,)
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.debug("bible cache read failed for %s: %s", ref, exc)
            return None
        return row[0] if row else None

    def _cache_put(self, ref: str, text: str) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO bible_verses (ref, text, translation) "
                    "VALUES (?, ?, ?)",
                    (ref, text, self.translation),
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.debug("bible cache write failed for %s: %s", ref, exc)

    def get(self, ref: str) -> Optional[Tuple[str, str]]:
        """Resolve one ref -> (display_ref, text). None when unresolvable."""
        parsed = parse_reference(ref, self.max_verses_per_ref)
        if parsed is None:
            logger.debug("unparseable scripture ref: %r", ref)
            return None
        book, chapter, start, end = parsed
        key = display_ref(book, chapter, start, end)

        cached = self._cache_get(key)
        if cached is not None:
            return key, cached

        text = self._from_bundle(book, chapter, start, end)
        if text is None:
            text = self._from_api(book, chapter, start, end)
        if text is None:
            return None
        self._cache_put(key, text)
        return key, text

    def get_many(self, refs: List[str], limit: int = 8) -> List[Tuple[str, str]]:
        """Resolve distinct refs in order, capped at `limit` resolved verses."""
        seen: set[str] = set()
        resolved: List[Tuple[str, str]] = []
        for ref in refs:
            if len(resolved) >= limit:
                break
            parsed = parse_reference(ref, self.max_verses_per_ref)
            if parsed is None:
                continue
            key = display_ref(*parsed)
            if key in seen:
                continue
            seen.add(key)
            hit = self.get(ref)
            if hit is not None:
                resolved.append(hit)
        return resolved

    async def aget_many(self, refs: List[str], limit: int = 8) -> List[Tuple[str, str]]:
        return await asyncio.to_thread(self.get_many, refs, limit)
