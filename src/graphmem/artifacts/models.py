from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Artifact:
    kind: Literal["issue", "pr"]
    number: int
    title: str
    body: str
    created_at: datetime
    files: list[str]
