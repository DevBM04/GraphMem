"""Call edge resolution for the Python Tree-sitter adapter."""
from __future__ import annotations

from typing import Optional
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.common.entity_builder import _ParsedFile
from graphmem.parsing.common.source_utils import DEFINITION_TYPES, STATEMENT_TYPES

class CallResolutionMixin:
        def _resolve_calls(self, parsed: ParsedRepository) -> None:
            for parsed_file in self._parsed_files:
                resolver = _TreeSitterCallResolver(
                    parser=self,
                    parsed=parsed,
                    parsed_file=parsed_file,
                )
                resolver.run()
                for relation in resolver.relations:
                    if not self._has_relation(parsed, relation):
                        parsed.add_relation(relation)

class _TreeSitterCallResolver:
    def __init__(self, *, parser: PythonParser, parsed: ParsedRepository, parsed_file: _ParsedFile):
        self.parser = parser
        self.parsed = parsed
        self.parsed_file = parsed_file
        self.record = parsed_file.record
        self.source = parsed_file.source
        self.relations: list[Relation] = []
        self.current_callable: Optional[CodeEntity] = None
        self.current_class: Optional[CodeEntity] = None
        self.current_statement: Optional[CodeEntity] = None
        self.statement_by_span = {
            (e.start_line, e.end_line): e
            for e in parsed.entities
            if e.type == EntityType.STATEMENT
            and e.path == self.record.relative_path
        }

    def run(self) -> None:
        self._visit(self.parsed_file.tree.root_node)

    def _visit(self, node) -> None:
        old_callable = self.current_callable
        old_class = self.current_class
        old_statement = self.current_statement

        if node.type in {"class_definition"}:
            entity = self._definition_entity(node)
            self.current_class = entity or self.current_class
        elif node.type in {"function_definition", "async_function_definition"}:
            self.current_callable = self._definition_entity(node)
        elif node.type in STATEMENT_TYPES:
            self.current_statement = self._statement_entity(node)

        if node.type == "call":
            self._handle_call(node)

        for child in node.named_children:
            # Definitions create their own scope, but nested methods/classes
            # still need to be visited.
            self._visit(child)

        self.current_callable = old_callable
        self.current_class = old_class
        self.current_statement = old_statement

    def _handle_call(self, node) -> None:
        function_node = node.child_by_field_name("function")
        if function_node is None:
            # Some grammar versions expose the callee as the first named child.
            function_node = node.named_children[0] if node.named_children else None
        if function_node is None:
            return

        target = self._resolve_target(function_node)
        source = self.current_statement or self.current_callable
        if target is None or source is None:
            return

        self.relations.append(Relation(
            source_id=source.id,
            target_id=target.id,
            type=RelationType.CALLS,
            metadata={
                "call": self.parser._node_text(node, self.source),
                "resolved_via": self._resolution_method(function_node),
            },
        ))

    def _definition_entity(self, node) -> Optional[CodeEntity]:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = self.parser._node_text(name_node, self.source)

        # Exact line/name match is robust and avoids ambiguities from overloads.
        candidates = [
            e for e in self.parsed.entities
            if e.path == self.record.relative_path
            and e.name == name
            and e.type in {EntityType.CLASS, EntityType.FUNCTION, EntityType.METHOD}
            and e.start_line == node.start_point[0] + 1
        ]
        return candidates[0] if candidates else None

    def _statement_entity(self, node) -> Optional[CodeEntity]:
        key = (node.start_point[0] + 1, node.end_point[0] + 1)
        return self.statement_by_span.get(key)

    def _resolve_target(self, function_node) -> Optional[CodeEntity]:
        if function_node.type == "identifier":
            return self._resolve_name(self.parser._node_text(function_node, self.source))

        if function_node.type == "attribute":
            attr = function_node.child_by_field_name("attribute")
            object_node = function_node.child_by_field_name("object")
            if attr is None or object_node is None:
                return None
            method = self.parser._node_text(attr, self.source)

            # self.foo()
            if object_node.type == "identifier":
                receiver = self.parser._node_text(object_node, self.source)
                if receiver == "self" and self.current_class:
                    return self.parser._entities_by_qualified_name.get(
                        f"{self.current_class.qualified_name}.{method}"
                    )

                # ClassA.foo()
                class_entity = self._resolve_name(receiver)
                if class_entity and class_entity.type == EntityType.CLASS:
                    return self.parser._entities_by_qualified_name.get(
                        f"{class_entity.qualified_name}.{method}"
                    )

                # obj.foo()
                inferred = self._infer_variable_class(receiver)
                if inferred:
                    return self.parser._entities_by_qualified_name.get(
                        f"{inferred.qualified_name}.{method}"
                    )

            # ClassA().foo()
            if object_node.type == "call":
                constructor = object_node.child_by_field_name("function")
                if constructor is None and object_node.named_children:
                    constructor = object_node.named_children[0]
                if constructor and constructor.type == "identifier":
                    class_entity = self._resolve_name(
                        self.parser._node_text(constructor, self.source)
                    )
                    if class_entity and class_entity.type == EntityType.CLASS:
                        return self.parser._entities_by_qualified_name.get(
                            f"{class_entity.qualified_name}.{method}"
                        )

        return None

    def _resolve_name(self, name: str) -> Optional[CodeEntity]:
        entity = self.parser._entities_by_file_and_name.get(
            (self.record.relative_path, name)
        )
        if entity:
            return entity

        imported = self.parser._imports_by_file.get(self.record.relative_path, {}).get(name)
        if imported:
            # Exact imported symbol.
            target = self.parser._entities_by_qualified_name.get(imported)
            if target:
                return target
            # Imported module/class name.
            module_name, _, symbol = imported.rpartition(".")
            if symbol:
                target = self.parser._entities_by_module_and_name.get((module_name, symbol))
                if target:
                    return target

        if self.current_class:
            target = self.parser._entities_by_qualified_name.get(
                f"{self.current_class.qualified_name}.{name}"
            )
            if target:
                return target

        matches = [
            entity for (module, symbol), entity
            in self.parser._entities_by_module_and_name.items()
            if symbol == name
        ]
        return matches[0] if len(matches) == 1 else None

    def _infer_variable_class(self, variable: str) -> Optional[CodeEntity]:
        # Search assignment statements before this call.
        call_line = self.current_statement.start_line if self.current_statement else 10**9
        candidates = [
            e for e in self.parsed.entities
            if e.type == EntityType.STATEMENT
            and e.path == self.record.relative_path
            and e.end_line is not None
            and e.end_line <= call_line
        ]
        for entity in sorted(candidates, key=lambda e: e.end_line or 0, reverse=True):
            text = entity.metadata.get("source", "")
            if not text.startswith(" "):
                # Keep source handling simple; Tree-sitter parsing below is
                # sufficient even when the original statement is multiline.
                pass
            # Parse only the statement with the same Tree-sitter parser.
            try:
                tree = self.parser._parser.parse(text.encode())
            except Exception:
                continue
            root = tree.root_node
            for node in self.parser._walk_named(root):
                if node.type != "assignment":
                    continue
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left is None or right is None or left.type != "identifier":
                    continue
                if self.parser._node_text(left, text.encode()) != variable:
                    continue
                if right.type == "call":
                    fn = right.child_by_field_name("function")
                    if fn and fn.type == "identifier":
                        return self._resolve_name(
                            self.parser._node_text(fn, text.encode())
                        )
        return None

    @staticmethod
    def _resolution_method(node) -> str:
        if node.type == "identifier":
            return "name"
        if node.type == "attribute":
            return "attribute"
        return "unknown"
