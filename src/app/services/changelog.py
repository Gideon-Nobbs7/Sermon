from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark")


def changelog_path() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "CHANGELOG.md"


@lru_cache(maxsize=1)
def render_changelog() -> str:
    path = changelog_path()
    if not path.exists():
        return "<p>The changelog is missing. See the repository docs folder.</p>"
    return _md.render(path.read_text(encoding="utf-8"))


def clear_changelog_cache() -> None:
    render_changelog.cache_clear()
