"""Shared lightweight records used while constructing parsed code entities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from graphmem.models.entities import CodeEntity

@dataclass
class _FileRecord:
    relative_path: str
    absolute_path: Path
    module_name: str
    entity_id: str

@dataclass
class _ParsedFile:
    record: _FileRecord
    tree: object
    source: bytes

@dataclass
class _Scope:
    entity: CodeEntity
    qualified_parts: list[str]
    kind: str  # file / class / function / method
