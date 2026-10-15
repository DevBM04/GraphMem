"""Small relation helpers shared by language-specific parsing passes."""
from __future__ import annotations

from graphmem.models.relations import Relation


def has_relation(parsed, relation: Relation) -> bool:
    """Return whether an equivalent source/target/type relation exists."""
    return any(
        existing.source_id == relation.source_id
        and existing.target_id == relation.target_id
        and existing.type == relation.type
        for existing in parsed.relations
    )


def add_relation_if_missing(parsed, relation: Relation) -> bool:
    """Add a relation unless an edge with the same endpoints and type exists."""
    if has_relation(parsed, relation):
        return False
    parsed.add_relation(relation)
    return True
