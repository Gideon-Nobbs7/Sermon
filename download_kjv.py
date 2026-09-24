"""Download the KJV bundle and convert it to the app's formatted JSON.

Source is the bolls.life KJV translation file (public domain text).
Strong's numbers and translator margin notes are stripped so lookups
return clean verse text.

Writes data/kjv.json shaped as:
    {"meta": {...}, "books": {"Genesis": {"1": {"1": "...", ...}, ...}, ...}}

    uv run download_kjv.py
    uv run download_kjv.py --out data/kjv.json
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

SOURCE_URL = "https://bolls.life/static/translations/KJV.json"

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

_TAG_RE = re.compile(r"<S>\d+</S>|<sup>.*?</sup>")
_WS_RE = re.compile(r"\s+")


def clean(text: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub("", text)).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and format the KJV bundle")
    parser.add_argument("--out", default="data/kjv.json", help="output path")
    parser.add_argument("--url", default=SOURCE_URL, help="source translation JSON")
    args = parser.parse_args()

    print(f"downloading {args.url} ...")
    with urllib.request.urlopen(args.url, timeout=120) as resp:
        raw = json.load(resp)
    print(f"source rows: {len(raw)}")

    books: dict[str, dict[str, dict[str, str]]] = {}
    for row in raw:
        book_no = row.get("book")
        if not isinstance(book_no, int) or not 1 <= book_no <= 66:
            continue
        name = BOOK_NAMES[book_no - 1]
        chapter = str(row["chapter"])
        verse = str(row["verse"])
        books.setdefault(name, {}).setdefault(chapter, {})[verse] = clean(row["text"])

    total = sum(len(v) for ch in books.values() for v in ch.values())
    print(f"canon verses: {total} across {len(books)} books")
    if total < 31000:
        raise SystemExit(f"unexpectedly few verses ({total}) - source may be broken")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "translation": "KJV",
            "source": SOURCE_URL,
            "books": len(books),
            "verses": total,
        },
        "books": books,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
