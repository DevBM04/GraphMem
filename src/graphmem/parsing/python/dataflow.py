"""Statement-level DEF/USE metadata and conservative data-flow edges."""
from __future__ import annotations

from typing import Optional
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.common.entity_builder import _ParsedFile
from graphmem.parsing.common.source_utils import DEFINITION_TYPES, STATEMENT_TYPES

class DataFlowMixin:
        def _build_dataflow(self, parsed: ParsedRepository) -> None:
            for parsed_file in self._parsed_files:
                analyzer = _TreeSitterDataFlowAnalyzer(
                    parser=self,
                    parsed=parsed,
                    parsed_file=parsed_file,
                )
                analyzer.run()
                for relation in analyzer.relations:
                    if not self._has_relation(parsed, relation):
                        parsed.add_relation(relation)

class _TreeSitterDataFlowAnalyzer:
    """Conservative intra-procedural DEF/USE analysis.

    This deliberately does not pretend to be a full CFG/fixed-point data-flow
    engine. It is the same useful MVP level as the previous AST parser:
    source-order local definitions with statement-level DEF/USE metadata.
    """

    def __init__(self, *, parser: PythonParser, parsed: ParsedRepository, parsed_file: _ParsedFile):
        self.parser = parser
        self.parsed = parsed
        self.parsed_file = parsed_file
        self.record = parsed_file.record
        self.source = parsed_file.source
        self.relations: list[Relation] = []
        self.statement_by_span = {
            (e.start_line, e.end_line): e
            for e in parsed.entities_in_file(self.record.relative_path)
            if e.type == EntityType.STATEMENT
        }

    def run(self) -> None:
        self._walk_scope(self.parsed_file.tree.root_node, {})

    def _walk_scope(self, node, last_definition: dict[str, Optional[CodeEntity]]):
        # File/module scope.
        for child in node.named_children:
            if child.type in {"function_definition", "async_function_definition"}:
                self._walk_function(child)
            elif child.type == "decorated_definition":
                definition = self.parser._first_child_of_types(child, DEFINITION_TYPES)
                if definition and definition.type in {"function_definition", "async_function_definition"}:
                    self._walk_function(definition)
                elif definition and definition.type == "class_definition":
                    self._walk_class(definition)
            elif child.type == "class_definition":
                self._walk_class(child)
            elif child.type in STATEMENT_TYPES:
                self._process_statement(child, last_definition)

    def _walk_class(self, node) -> None:
        body = node.child_by_field_name("body")
        if body is None:
            return
        # Class-level definitions don't flow into method locals.
        for child in body.named_children:
            if child.type in {"function_definition", "async_function_definition"}:
                self._walk_function(child)
            elif child.type == "decorated_definition":
                definition = self.parser._first_child_of_types(child, DEFINITION_TYPES)
                if definition and definition.type in {"function_definition", "async_function_definition"}:
                    self._walk_function(definition)

    def _walk_function(self, node) -> None:
        definitions: dict[str, Optional[CodeEntity]] = {}
        parameters = node.child_by_field_name("parameters")
        if parameters:
            for child in parameters.named_children:
                if child.type == "identifier":
                    definitions[self.parser._node_text(child, self.source)] = None
                elif child.type in {"typed_parameter", "default_parameter", "typed_default_parameter", "list_splat_pattern", "dictionary_splat_pattern"}:
                    name_node = child.child_by_field_name("name")
                    if name_node is None and child.named_children:
                        name_node = child.named_children[0]
                    if name_node and name_node.type == "identifier":
                        definitions[self.parser._node_text(name_node, self.source)] = None

        body = node.child_by_field_name("body")
        if body is None:
            return
        for child in body.named_children:
            if child.type in {"function_definition", "async_function_definition", "class_definition", "decorated_definition"}:
                # Nested defs are separate scopes.
                if child.type == "class_definition":
                    self._walk_class(child)
                elif child.type == "decorated_definition":
                    definition = self.parser._first_child_of_types(child, DEFINITION_TYPES)
                    if definition:
                        if definition.type == "class_definition":
                            self._walk_class(definition)
                        else:
                            self._walk_function(definition)
                else:
                    self._walk_function(child)
                continue
            if child.type in STATEMENT_TYPES:
                self._process_statement(child, definitions)

    def _process_statement(self, node, last_definition: dict[str, Optional[CodeEntity]]):
        entity = self.statement_by_span.get((
            node.start_point[0] + 1,
            node.end_point[0] + 1,
        ))
        if entity is None:
            return

        uses, defines = self._extract_def_use(node)
        entity.metadata["uses"] = sorted(uses)
        entity.metadata["defines"] = sorted(defines)

        # Resolve uses against definitions that existed before this statement.
        for name in sorted(uses):
            definition = last_definition.get(name, "__UNDEFINED__")
            if definition not in (None, "__UNDEFINED__"):
                self.relations.append(Relation(
                    source_id=definition.id,
                    target_id=entity.id,
                    type=RelationType.DATAFLOW_DEF_USE,
                    metadata={"variable": name, "direction": "def_to_use"},
                ))

        # Definitions become available after the statement.
        for name in defines:
            last_definition[name] = entity

        # Descend into compound statement bodies. The parent statement itself
        # remains the statement representing the condition/header.
        for child in self._nested_statement_children(node):
            self._process_statement(child, last_definition)

    def _extract_def_use(self, node):
        uses: set[str] = set()
        defines: set[str] = set()

        if node.type == "expression_statement":
            children = node.named_children

            if len(children) == 1 and children[0].type in {
                "assignment",
                "augmented_assignment",
            }:
                return self._extract_def_use(children[0])
    
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                defines.update(self._store_names(left))
            if right:
                uses.update(self._load_names(right))
            return uses, defines

        if node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                names = self._load_names(left)
                uses.update(names)
                defines.update(self._store_names(left))
            if right:
                uses.update(self._load_names(right))
            return uses, defines

        if node.type == "for_statement":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                defines.update(self._store_names(left))
            if right:
                uses.update(self._load_names(right))
            return uses, defines

        if node.type in {"import_statement", "import_from_statement"}:
            # Imports define their local aliases. Detailed import edges are
            # handled separately.
            if node.type == "import_statement":
                for child in node.named_children:
                    if child.type == "aliased_import":
                        alias = child.child_by_field_name("alias")
                        name = child.child_by_field_name("name")
                        local = alias or name
                        if local:
                            defines.add(self.parser._node_text(local, self.source).split(".")[0])
                    elif child.type == "dotted_name":
                        defines.add(self.parser._node_text(child, self.source).split(".")[0])
            return uses, defines

        if node.type == "with_statement":
            for child in node.named_children:
                if child.type == "with_clause":
                    uses.update(self._load_names(child))
                elif child.type in {"as_pattern", "as_pattern_target"}:
                    defines.update(self._store_names(child))
            return uses, defines

        # For return/if/while/expression/raise/assert/etc., every identifier
        # is a use unless it occurs in a store position under an assignment.
        uses.update(self._load_names(node))
        return uses, defines

    def _load_names(self, node):
        result = set()
        for current in self.parser._walk_named(node):
            if current.type != "identifier":
                continue
            if self._is_assignment_target(current):
                continue
            result.add(self.parser._node_text(current, self.source))
        return result

    def _store_names(self, node):
        result = set()
        for current in self.parser._walk_named(node):
            if current.type == "identifier":
                result.add(self.parser._node_text(current, self.source))
        return result

    def _is_assignment_target(self, identifier) -> bool:
        parent = identifier.parent
        if parent is None:
            return False
        # Walk up through patterns until the relevant assignment node.
        current = parent
        for _ in range(6):
            if current is None:
                return False
            if current.type in {"assignment", "augmented_assignment", "for_statement"}:
                left = current.child_by_field_name("left")
                return left is not None and self._contains_node(left, identifier)
            if current.type in {"return_statement", "expression_statement", "call"}:
                return False
            current = current.parent
        return False

    @staticmethod
    def _contains_node(root, needle) -> bool:
        if root.id == needle.id:
            return True
        return any(_TreeSitterDataFlowAnalyzer._contains_node(c, needle) for c in root.named_children)

    def _nested_statement_children(self, node):
        result = []
        for child in node.named_children:
            if child.type in DEFINITION_TYPES or child.type == "decorated_definition":
                continue
            if child.type in STATEMENT_TYPES:
                result.append(child)
            elif child.type in {
                "block", "else_clause", "elif_clause", "finally_clause",
                "except_clause", "case_clause",
            }:
                for nested in child.named_children:
                    if nested.type in STATEMENT_TYPES:
                        result.append(nested)
        return result
