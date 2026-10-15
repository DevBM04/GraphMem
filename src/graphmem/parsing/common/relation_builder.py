"""Small relation helpers shared by language-specific parsing passes."""
from __future__ import annotations

from graphmem.models.relations import Relation


def has_relation(parsed, relation: Relation) -> bool:
    """O(1) check for an equivalent source/target/type relation."""
    return parsed.has_relation(relation)


def add_relation_if_missing(parsed, relation: Relation) -> bool:
    if parsed.has_relation(relation):
        return False
    parsed.add_relation(relation)
    return True