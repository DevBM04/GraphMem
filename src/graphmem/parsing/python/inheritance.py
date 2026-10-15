"""Inheritance extraction and resolution for the Tree-sitter Python parser."""
from __future__ import annotations

from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.parsing.common.relation_builder import add_relation_if_missing


def extract_base_names(base_node, source: bytes) -> list[str]:
    """Return source spellings for a class definition's base expressions."""
    if base_node is None:
        return []
    return [
        source[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip()
        for child in base_node.named_children
    ]


class InheritanceMixin:
    """Resolve class base expressions to class entities and emit INHERITS edges.

    Edge direction is subclass -> superclass. Names are resolved conservatively:
    local classes, imported symbols/aliases, qualified names, and unique global
    class-name matches are supported. Ambiguous or external bases are ignored.
    """

    def _resolve_inheritance(self, parsed) -> None:
        classes = [e for e in parsed.entities if e.type == EntityType.CLASS]
        classes_by_name: dict[str, list[CodeEntity]] = {}
        for entity in classes:
            classes_by_name.setdefault(entity.name, []).append(entity)

        for child in classes:
            for base_expression in child.metadata.get("bases", []):
                base = self._resolve_base_class(
                    base_expression=base_expression,
                    child=child,
                    classes_by_name=classes_by_name,
                )
                if base is None or base.id == child.id:
                    continue
                add_relation_if_missing(parsed, Relation(
                    source_id=child.id,
                    target_id=base.id,
                    type=RelationType.INHERITS,
                    metadata={
                        "base_expression": base_expression,
                        "resolved_via": self._base_resolution_method(
                            base_expression, child, base
                        ),
                    },
                ))

    def _resolve_base_class(
        self,
        *,
        base_expression: str,
        child: CodeEntity,
        classes_by_name: dict[str, list[CodeEntity]],
    ) -> CodeEntity | None:
        """Resolve a base expression without guessing between ambiguous classes."""
        expression = base_expression.strip()
        if not expression:
            return None

        # A base can be written as `module.Base`; use the final attribute as a
        # candidate only after trying the full qualified expression.
        qualified = self._entities_by_qualified_name.get(expression)
        if qualified and qualified.type == EntityType.CLASS:
            return qualified

        file_path = child.path or ""
        imported = self._imports_by_file.get(file_path, {}).get(expression)
        if imported:
            resolved = self._resolve_imported_symbol(imported)
            if resolved and resolved.type == EntityType.CLASS:
                return resolved

        # Unqualified names declared in the same file take precedence.
        same_file = self._entities_by_file_and_name.get((file_path, expression))
        if same_file and same_file.type == EntityType.CLASS:
            return same_file

        # Resolve `alias.Base` when `alias` was imported as a module.
        if "." in expression:
            first, _, rest = expression.partition(".")
            module_alias = self._imports_by_file.get(file_path, {}).get(first)
            if module_alias:
                qualified_name = f"{module_alias}.{rest}"
                resolved = self._entities_by_qualified_name.get(qualified_name)
                if resolved and resolved.type == EntityType.CLASS:
                    return resolved
                module, _, symbol = qualified_name.rpartition(".")
                resolved = self._entities_by_module_and_name.get((module, symbol))
                if resolved and resolved.type == EntityType.CLASS:
                    return resolved

        candidates = classes_by_name.get(expression, [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _resolve_imported_symbol(self, imported: str) -> CodeEntity | None:
        target = self._entities_by_qualified_name.get(imported)
        if target is not None:
            return target
        module_name, _, symbol_name = imported.rpartition(".")
        if module_name and symbol_name:
            target = self._entities_by_module_and_name.get((module_name, symbol_name))
            if target is not None:
                return target
        return None

    @staticmethod
    def _base_resolution_method(base_expression: str, child: CodeEntity, base: CodeEntity) -> str:
        if "." in base_expression:
            return "qualified_or_module_alias"
        if child.path == base.path:
            return "same_file_name"
        return "import_or_unique_name"
