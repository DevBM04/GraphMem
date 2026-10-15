"""Build indexes over parsed class/function/method entities."""
from __future__ import annotations

from graphmem.models.entities import EntityType


def build_symbol_indexes(parsed):
    """Return qualified-name, file/name, and module/name indexes."""
    by_qualified_name = {}
    by_file_and_name = {}
    by_module_and_name = {}
    file_by_path = {
        entity.path: entity
        for entity in parsed.entities
        if entity.type == EntityType.FILE
    }
    for entity in parsed.entities:
        if entity.type not in {EntityType.CLASS, EntityType.FUNCTION, EntityType.METHOD}:
            continue
        if entity.qualified_name:
            by_qualified_name[entity.qualified_name] = entity
        if entity.path:
            by_file_and_name.setdefault((entity.path, entity.name), entity)
            file_entity = file_by_path.get(entity.path)
            if file_entity and file_entity.qualified_name:
                by_module_and_name[(file_entity.qualified_name, entity.name)] = entity
    return by_qualified_name, by_file_and_name, by_module_and_name
