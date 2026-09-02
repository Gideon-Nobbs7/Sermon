from dataclasses import dataclass, field
from typing import List


@dataclass
class Answer:
    answer: str
    sources: List[dict] = field(default_factory=list)