"""Custom parser for the church sermon markdown format.

Reads `2026-Sermons.md` — the hand-written style — and extracts one
`Chunk` per sermon section.

    ### 8th Feb, 2026 ###                                date heading
    ### 5th Apr, 2026 - Praying For The Nation Ghana ### date + title
    #### Exhortation: Ps. Derrick - The Spirit of Excellence ####   section
     - bullet notes...
    ##### The Spirit of Might #####                     sub-heading (stays in notes)

Section headers: `Type: Speaker - Title`, `Type: Speaker`, `Type: Speaker: Title`,
`Speaker - Title`, or `Speaker` only. A date block with no sections becomes one
`General` chunk.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from ..schemas.sermon import Chunk

# Month map for date parsing
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Book names, ordered so longer/more-specific alternatives are tried first.
_BOOK_NAMES = (
    r"(?:[1-3]\s*)?"
    r"(?:"
    r"Gen(?:esis)?|Exod?(?:us)?|Lev(?:iticus)?|Num(?:bers)?"
    r"|Deut?(?:eronomy)?|Josh(?:ua)?|Judg(?:es)?|Ruth"
    r"|1\s*Sam(?:uel)?|2\s*Sam(?:uel)?"
    r"|1\s*K(?:in)?gs|2\s*K(?:in)?gs"
    r"|1\s*Chr(?:onicles)?|2\s*Chr(?:onicles)?"
    r"|Ezra|Neh(?:emiah)?|Esth(?:er)?|Job"
    r"|Ps(?:alm)?(?:s)?|Prov?(?:erbs)?|Eccl(?:esiastes)?"
    r"|Song|Isa(?:iah)?|Is|Jer(?:emiah)?|Lam(?:entations)?"
    r"|Ezek(?:iel)?|Dan(?:iel)?"
    r"|Hos(?:ea)?|Joel|Amos|Obad(?:iah)?|Jon(?:ah)?"
    r"|Mic(?:ah)?|Nah(?:um)?|Hab(?:akkuk)?|Zeph(?:aniah)?"
    r"|Hag(?:gai)?|Zech(?:ariah)?|Mal(?:achi)?"
    r"|Matt?(?:hew)?|Matth|Mark|Luke|John|Acts"
    r"|Rom(?:ans)?|1\s*Cor(?:inthians)?|2\s*Cor(?:inthians)?"
    r"|Gal(?:atians)?|Eph(?:esians)?|Phili?(?:ppians)?|Col(?:ossians)?"
    r"|1\s*Thess?(?:alonians)?|2\s*Thess?(?:alonians)?"
    r"|1\s*Tim(?:othy)?|2\s*Tim(?:othy)?"
    r"|Tit(?:us)?|Philem?(?:on)?|Heb(?:rews)?"
    r"|Jam(?:es)?|1\s*Pet(?:er)?|2\s*Pet(?:er)?"
    r"|1\s*John|2\s*John|3\s*John|Jude"
    r"|Rev(?:elation)?"
    r")"
)

_SCRIPTURE_RE = re.compile(
    r"\b" + _BOOK_NAMES +
    r"(?:\s*\.\s*|\s+)"          # separator: space or "1 Cor." style dot
    r"\d+"                        # chapter
    r":*:"                        # colon (tolerate double-colon typos)
    r"\d+"                        # verse
    r"(?:-\d+)?"                  # optional verse range
)


class SermonMarkdownParser:
    """Regex-based parser for the `2026-Sermons.md` markdown format."""

    _DATE_RE = re.compile(r"^###\s+(.+?)\s+###\s*$", re.MULTILINE)
    _SECTION_HEADER_RE = re.compile(r"^####\s+(.+?)\s+####\s*$", re.MULTILINE)
    _BARE_HASH_LINE_RE = re.compile(r"^\s*#+\s*$", re.MULTILINE)

    def parse_file(self, filepath: str) -> List[Chunk]:
        with open(filepath, "r", encoding="utf-8") as f:
            return self.parse_text(f.read())

    def parse_text(self, text: str) -> List[Chunk]:
        chunks: List[Chunk] = []
        for date_str, block_text in self._split_by_date(text):
            iso_date = self._parse_date(date_str)
            sections = self._split_by_section(block_text)

            if not sections:
                chunks.append(self._make_chunk(
                    iso_date,
                    topic_type="General",
                    speaker="Unknown",
                    topic_title="",
                    notes=block_text,
                    index=0,
                ))
                continue

            for idx, (header, notes) in enumerate(sections):
                topic_type, speaker, topic_title = self._parse_header(header)
                chunks.append(self._make_chunk(
                    iso_date, topic_type, speaker, topic_title, notes, idx,
                ))
        return chunks

    def _make_chunk(self, iso_date, topic_type, speaker, topic_title,
                    notes, index) -> Chunk:
        notes = self._clean_notes(notes)
        scriptures = self._extract_scriptures(notes)
        type_key = topic_type.lower().replace(" ", "_")
        return Chunk(
            id=f"{iso_date}_{type_key}_{index}",
            source_file="",
            date=iso_date,
            topic_type=topic_type,
            speaker=speaker,
            topic_title=topic_title,
            scriptures=scriptures,
            text=notes,
        )

    def _split_by_date(self, text: str) -> List[Tuple[str, str]]:
        matches = list(self._DATE_RE.finditer(text))
        blocks = []
        for i, m in enumerate(matches):
            date_str = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            blocks.append((date_str, text[start:end].strip()))
        return blocks

    def _split_by_section(self, text: str) -> List[Tuple[str, str]]:
        matches = list(self._SECTION_HEADER_RE.finditer(text))
        sections = []
        for i, m in enumerate(matches):
            header = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append((header, text[start:end].strip()))
        return sections

    def _parse_header(self, header: str) -> Tuple[str, str, str]:
        """Split a section header into (topic_type, speaker, topic_title)."""
        topic_type = "General"
        speaker = "Unknown"
        topic_title = ""

        m = re.match(r"^(.+?):\s*(.+?)\s*-\s*(.*)$", header)
        if m and m.group(3).strip():
            return (m.group(1).strip(), m.group(2).strip(), m.group(3).strip())

        m = re.match(r"^(.+?):\s*(.+?):\s*(.+)$", header)
        if m:
            return (m.group(1).strip(), m.group(2).strip(), m.group(3).strip())

        m = re.match(r"^(.+?):\s*(.+)$", header)
        if m:
            speaker = re.sub(r"\s*-\s*$", "", m.group(2)).strip()
            return (m.group(1).strip(), speaker, topic_title)

        m = re.match(r"^(.+?)\s*-\s*(.+)$", header)
        if m:
            return (topic_type, m.group(1).strip(), m.group(2).strip())

        speaker = header.strip()
        return (topic_type, speaker, topic_title)

    def _extract_scriptures(self, text: str) -> List[str]:
        seen = set()
        unique = []
        for m in _SCRIPTURE_RE.findall(text):
            ref = re.sub(r"::+", ":", m.strip())
            if ref and ref not in seen:
                seen.add(ref)
                unique.append(ref)
        return unique

    def _parse_date(self, date_str: str) -> str:
        """Parse "8th Feb, 2026" -> "2026-02-08".

        Tolerates a trailing title ("5th Apr, 2026 - Praying For The Nation
        Ghana") and a missing year (defaults to 2026).
        """
        date_str = date_str.split("-")[0].strip()
        date_str = date_str.split(",")[0].strip()
        parts = date_str.split()
        if not parts:
            raise ValueError(f"cannot parse date: {date_str!r}")

        day = int(re.sub(r"(st|nd|rd|th)", "", parts[0]))
        month = _MONTHS.get(parts[1][:3].lower(), 1) if len(parts) > 1 else 1
        year = int(parts[2]) if len(parts) > 2 else 2026
        return f"{year:04d}-{month:02d}-{day:02d}"

    @staticmethod
    def _clean_notes(notes: str) -> str:
        """Drop lone '#' separator lines that don't belong to the notes."""
        return re.sub(r"^\s*#+\s*$\n?", "", notes, flags=re.MULTILINE).strip()
