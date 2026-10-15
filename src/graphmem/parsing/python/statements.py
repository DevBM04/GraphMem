"""Fine-grained statement entity extraction helpers."""
from __future__ import annotations

from pathlib import PurePosixPath
from platform import node
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.parsing.common.entity_builder import _FileRecord, _Scope
from graphmem.parsing.common.source_utils import DEFINITION_TYPES, STATEMENT_TYPES

class StatementMixin:
        @staticmethod
        def _is_statement_node(node) -> bool:
            return node.type in STATEMENT_TYPES and node.type != "comment"

        @staticmethod
        def _is_docstring_statement(node) -> bool:
            if node.type != "expression_statement":
                return False

            children = node.named_children

            return (
                len(children) == 1
                and children[0].type in {"string", "concatenated_string"}
            )

        @staticmethod
        def _nested_statement_children(node):
            """Return direct/nested statement nodes without entering definitions."""
            result = []

            def collect(n):
                for child in n.named_children:
                    if child.type in DEFINITION_TYPES or child.type == "decorated_definition":
                        continue
                    if child.type in STATEMENT_TYPES:
                        result.append(child)
                    elif child.type in {
                        "block", "else_clause", "elif_clause", "finally_clause",
                        "except_clause", "case_clause", "conditional_expression",
                    }:
                        collect(child)
                    elif child.type.endswith("_clause"):
                        collect(child)

            # For a compound statement, its body/clauses contain statements.
            collect(node)
            # The node itself may appear through unusual grammar nesting; avoid it.
            return [n for n in result if n.id != node.id]

        def _add_statement(
            self,
            *,
            node,
            scope: _Scope,
            record: _FileRecord,
            repo_name: str,
            version: str,
            source: bytes,
            number: int,
            parsed: ParsedRepository,
        ) -> CodeEntity:
            source_text = self._node_text(node, source)
            qualified_scope = ".".join(scope.qualified_parts) or record.module_name
            qualified_name = f"{qualified_scope}::statement_{number}"
            entity_id = self.make_entity_id(
                repo_name,
                record.relative_path,
                version,
                qualified_name=qualified_name,
            )
            entity = CodeEntity(
                id=entity_id,
                type=EntityType.STATEMENT,
                name=self._statement_name(source_text, number),
                path=record.relative_path,
                qualified_name=qualified_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent_id=scope.entity.id,
                metadata={
                    "language": self.language,
                    "version": version,
                    "parser": "tree-sitter",
                    "ast_type": node.type,
                    "source": source_text,
                    "statement_index": number,
                    "tree_sitter_start_byte": node.start_byte,
                    "tree_sitter_end_byte": node.end_byte,
                    "uses": [],
                    "defines": [],
                },
            )
            parsed.add_entity(entity)
            parsed.add_relation(Relation(
                source_id=scope.entity.id,
                target_id=entity_id,
                type=RelationType.CONTAINS,
            ))
            return entity

        @staticmethod
        def _statement_name(text: str, number: int) -> str:
            text = " ".join(text.strip().split())
            if len(text) > 80:
                return text[:77] + "..."
            return text or f"statement_{number}"
