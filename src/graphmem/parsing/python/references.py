"""Symbol indexes and conservative REFERENCES-edge resolution."""
from __future__ import annotations

from graphmem.models.entities import EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.parsing.common.symbol_table import build_symbol_indexes
from graphmem.parsing.common.relation_builder import add_relation_if_missing, has_relation


class ReferenceMixin:
    """Build symbol indexes and connect statements to referenced code symbols.

    CALLS edges remain the representation for call expressions. REFERENCES is
    used for other resolved identifier uses (for example, a class used as a
    value or a function passed as an argument). External and ambiguous names
    are deliberately not linked.
    """

    def _build_symbol_indexes(self, parsed) -> None:
        (
            self._entities_by_qualified_name,
            self._entities_by_file_and_name,
            self._entities_by_module_and_name,
        ) = build_symbol_indexes(parsed)

        # symbol name -> all entities with that name (replaces O(n) scans)
        by_symbol: dict[str, list] = {}
        for (_, symbol), entity in self._entities_by_module_and_name.items():
            by_symbol.setdefault(symbol, []).append(entity)
        self._entities_by_symbol_name = by_symbol

    def _has_relation(self, parsed, relation: Relation) -> bool:
        return has_relation(parsed, relation)

    def _resolve_references(self, parsed) -> None:
        symbol_types = {EntityType.CLASS, EntityType.FUNCTION, EntityType.METHOD}

        for parsed_file in self._parsed_files:
            record = parsed_file.record
            source = parsed_file.source
            root = parsed_file.tree.root_node
            statement_entities = {
                (e.start_line, e.end_line): e
                for e in parsed.entities_in_file(record.relative_path)
                if e.type == EntityType.STATEMENT
            }

            for node in self._walk_named(root):
                if node.type not in {"identifier", "attribute"}:
                    continue

                # The actual call expression is represented by CALLS. Avoid
                # adding a duplicate REFERENCES edge for its callee.
                if self._is_call_callee(node):
                    continue

                # Attribute expressions are considered as a whole only when
                # they resolve as a symbol; do not separately link each token.
                name = self._node_text(node, source).strip()
                target = self._resolve_reference_name(name, record.relative_path)
                if target is None or target.type not in symbol_types:
                    continue

                statement = self._statement_for_node(node, statement_entities)
                if statement is None or statement.id == target.id:
                    continue

                add_relation_if_missing(parsed, Relation(
                    source_id=statement.id,
                    target_id=target.id,
                    type=RelationType.REFERENCES,
                    metadata={
                        "reference": name,
                        "line": node.start_point[0] + 1,
                        "resolved_via": self._reference_resolution_method(
                            name, record.relative_path, target
                        ),
                    },
                ))

    def _resolve_reference_name(self, name: str, relative_path: str):
        if not name:
            return None

        # Exact qualified entity names first.
        target = self._entities_by_qualified_name.get(name)
        if target is not None:
            return target

        aliases = self._imports_by_file.get(relative_path, {})
        imported = aliases.get(name)
        if imported:
            target = self._resolve_imported_symbol(imported)
            if target is not None:
                return target

        # Local-file names are preferred over cross-repository guesses.
        target = self._entities_by_file_and_name.get((relative_path, name))
        if target is not None:
            return target

        # Resolve module-qualified expressions and module aliases.
        if "." in name:
            first, _, rest = name.partition(".")
            module_alias = aliases.get(first)
            if module_alias:
                imported_name = f"{module_alias}.{rest}"
                target = self._resolve_imported_symbol(imported_name)
                if target is not None:
                    return target
            module, _, symbol = name.rpartition(".")
            target = self._entities_by_module_and_name.get((module, symbol))
            if target is not None:
                return target

        matches = self._entities_by_symbol_name.get(name, [])
        return matches[0] if len(matches) == 1 else None

    def _resolve_imported_symbol(self, imported: str):
        target = self._entities_by_qualified_name.get(imported)
        if target is not None:
            return target
        module, _, symbol = imported.rpartition(".")
        if module and symbol:
            return self._entities_by_module_and_name.get((module, symbol))
        return None

    @staticmethod
    def _is_call_callee(node) -> bool:
        current = node
        parent = current.parent
        # Walk through attribute/call wrappers to determine whether this node
        # contributes to a call's `function` field.
        while parent is not None:
            if parent.type == "call":
                function_node = parent.child_by_field_name("function")
                if function_node is not None and (
                    function_node.id == current.id
                    or ReferenceMixin._contains_node(function_node, current)
                ):
                    return True
                return False
            if parent.type in {
                "expression_statement", "assignment", "return_statement",
                "argument_list", "block", "module",
            }:
                return False
            current, parent = parent, parent.parent
        return False

    @staticmethod
    def _contains_node(root, needle) -> bool:
        if root.id == needle.id:
            return True
        return any(ReferenceMixin._contains_node(child, needle) for child in root.named_children)

    def _statement_for_node(self, node, statement_entities):
        current = node
        while current is not None:
            if current.type in self._statement_types_for_references():
                key = (current.start_point[0] + 1, current.end_point[0] + 1)
                statement = statement_entities.get(key)
                if statement is not None:
                    return statement
            current = current.parent
        return None

    @staticmethod
    def _statement_types_for_references() -> set[str]:
        from graphmem.parsing.common.source_utils import STATEMENT_TYPES
        return STATEMENT_TYPES

    @staticmethod
    def _reference_resolution_method(name: str, relative_path: str, target) -> str:
        if "." in name:
            return "qualified_name"
        if target.path == relative_path:
            return "same_file_symbol"
        return "import_or_unique_symbol"
