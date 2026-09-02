from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceType(str, Enum):
    SERMON = "sermon"
    DOCUMENT = "document"


@dataclass
class Chunk:
    id: str
    source_file: str
    text: str
    source_type: SourceType = SourceType.SERMON

    # sermon-specific metadata (None for documents)
    date: Optional[str] = None
    speaker: Optional[str] = None
    topic_type: Optional[str] = None
    topic_title: Optional[str] = None
    scriptures: list[str] = field(default_factory=list)

    # document-specific metadata (None for sermons)
    page: Optional[int] = None
