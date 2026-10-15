"""Tree-sitter extraction of definitions, files, and parser diagnostics."""
from __future__ import annotations

from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.common.entity_builder import _FileRecord, _Scope, _ParsedFile
from graphmem.parsing.common.source_utils import DEFINITION_TYPES, STATEMENT_TYPES
from graphmem.parsing.python.inheritance import extract_base_names

class EntityExtractionMixin:
        def _parse_file(
            self,
            *,
            record: _FileRecord,
            repo_name: str,
            version: str,
            module_map: dict[str, _FileRecord],
            parsed: ParsedRepository,
        ) -> None:
            file_entity = parsed.get_entity(record.entity_id)
            if file_entity is None:
                return

            try:
                source = record.absolute_path.read_bytes()
            except OSError as exc:
                file_entity.metadata["read_error"] = str(exc)
                return

            try:
                tree = self._parser.parse(source)
            except Exception as exc:
                file_entity.metadata["parse_error"] = str(exc)
                return

            self._parsed_files.append(_ParsedFile(record, tree, source))

            error_nodes = self._find_error_nodes(tree.root_node)
            if error_nodes:
                file_entity.metadata["parse_errors"] = [
                    {
                        "type": n.type,
                        "start_line": n.start_point[0] + 1,
                        "end_line": n.end_point[0] + 1,
                        "text": self._node_text(n, source)[:200],
                    }
                    for n in error_nodes[:50]
                ]

            # Create all definitions and statements.
            self._extract_scope(
                root=tree.root_node,
                file_entity=file_entity,
                record=record,
                repo_name=repo_name,
                version=version,
                source=source,
                parsed=parsed,
            )

            self._extract_imports(
                tree=tree.root_node,
                record=record,
                module_map=module_map,
                file_entity=file_entity,
                parsed=parsed,
                source=source,
            )

        def _extract_scope(
            self,
            *,
            root,
            file_entity: CodeEntity,
            record: _FileRecord,
            repo_name: str,
            version: str,
            source: bytes,
            parsed: ParsedRepository,
        ) -> None:
            statement_counter = [0]

            def process_nodes(nodes, scope: _Scope) -> None:
                for node in nodes:
                    # Decorated definitions are wrappers in Tree-sitter.  The
                    # actual class/function is in the definition child.
                    if node.type == "decorated_definition":
                        definition = self._first_child_of_types(
                            node, DEFINITION_TYPES
                        )
                        if definition is not None:
                            process_definition(definition, scope)
                        continue

                    if node.type in DEFINITION_TYPES:
                        process_definition(node, scope)
                        continue

                    if self._is_statement_node(node) and not self._is_docstring_statement(node):
                        statement_counter[0] += 1
                        statement = self._add_statement(
                            node=node,
                            scope=scope,
                            record=record,
                            repo_name=repo_name,
                            version=version,
                            source=source,
                            number=statement_counter[0],
                            parsed=parsed,
                        )

                        # Compound statements contain nested statements.  Do
                        # not descend into expressions here, only actual nested
                        # statement-bearing children.
                        for child in self._nested_statement_children(node):
                            process_nodes([child], scope)
                        continue

                    # Module/class/function bodies are handled explicitly. For
                    # wrappers such as suite, just descend to find statements.
                    for child in node.named_children:
                        if child.type in DEFINITION_TYPES or self._is_statement_node(child):
                            process_nodes([child], scope)

            def process_definition(node, parent_scope: _Scope) -> None:
                name_node = node.child_by_field_name("name")
                if name_node is None:
                    return
                name = self._node_text(name_node, source)
                is_class = node.type == "class_definition"
                entity_type = EntityType.CLASS if is_class else (
                    EntityType.METHOD
                    if parent_scope.kind == "class"
                    else EntityType.FUNCTION
                )

                qualified_parts = parent_scope.qualified_parts + [name]
                qualified_name = ".".join(qualified_parts)
                entity_id = self.make_entity_id(
                    repo_name,
                    record.relative_path,
                    version,
                    qualified_name=qualified_name,
                )

                metadata = {
                    "language": self.language,
                    "version": version,
                    "parser": "tree-sitter",
                    "decorators": [],
                }
                if is_class:
                    bases = node.child_by_field_name("superclasses")
                    if bases is not None:
                        metadata["bases"] = extract_base_names(bases, source)

                entity = CodeEntity(
                    id=entity_id,
                    type=entity_type,
                    name=name,
                    path=record.relative_path,
                    qualified_name=qualified_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    parent_id=parent_scope.entity.id,
                    metadata=metadata,
                )
                parsed.add_entity(entity)
                parsed.add_relation(Relation(
                    source_id=parent_scope.entity.id,
                    target_id=entity_id,
                    type=RelationType.CONTAINS,
                ))

                child_scope = _Scope(
                    entity=entity,
                    qualified_parts=qualified_parts,
                    kind="class" if is_class else "function",
                )

                body = node.child_by_field_name("body")
                if body is not None:
                    process_nodes(body.named_children, child_scope)

            root_scope = _Scope(
                entity=file_entity,
                qualified_parts=[],
                kind="file",
            )
            process_nodes(root.named_children, root_scope)

        @staticmethod
        def _node_text(node, source: bytes) -> str:
            return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

        def _walk_named(self, node):
            yield node
            for child in node.named_children:
                yield from self._walk_named(child)

        def _find_error_nodes(self, node):
            result = []
            for current in self._walk_named(node):
                if current.type == "ERROR" or current.is_missing:
                    result.append(current)
            return result

        @staticmethod
        def _first_child_of_types(node, types: set[str]):
            for child in node.named_children:
                if child.type in types:
                    return child
            return None
