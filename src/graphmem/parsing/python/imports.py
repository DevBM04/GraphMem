"""Python import extraction, alias tracking, and module resolution."""
from __future__ import annotations

from graphmem.models.entities import CodeEntity
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.common.entity_builder import _FileRecord

class ImportMixin:
        def _extract_imports(
            self,
            *,
            tree,
            record: _FileRecord,
            module_map: dict[str, _FileRecord],
            file_entity: CodeEntity,
            parsed: ParsedRepository,
            source: bytes,
        ) -> None:
            aliases: dict[str, str] = {}

            current_package = (
                record.module_name.rsplit(".", 1)[0]
                if "." in record.module_name
                else ""
            )

            if record.absolute_path.name == "__init__.py":
                current_package = record.module_name

            for node in self._walk_named(tree):
                # --------------------------------------------------------------
                # import os
                # import pkg.sub.helpers
                # --------------------------------------------------------------
                if node.type == "import_statement":
                    raw = self._node_text(node, source)
                    file_entity.metadata.setdefault("imports", []).append(raw)

                    for imported in self._import_statement_names(node, source):
                        module = imported["module"]
                        local = imported["local"]

                        aliases[local] = module

                        target = module_map.get(module)

                        if target is not None and target.entity_id != record.entity_id:
                            parsed.add_relation(Relation(
                                source_id=record.entity_id,
                                target_id=target.entity_id,
                                type=RelationType.IMPORTS,
                                metadata={
                                    "resolved_via": "module_path_match",
                                    "imported": module,
                                },
                            ))

                # --------------------------------------------------------------
                # from .base import Base
                # from pkg.sub.helpers import normalize
                # --------------------------------------------------------------
                elif node.type == "import_from_statement":
                    raw = self._node_text(node, source)
                    file_entity.metadata.setdefault("imports", []).append(raw)

                    module = ""
                    level = 0

                    # Find the relative_import / module portion
                    for child in node.named_children:

                        if child.type == "relative_import":
                            text = self._node_text(child, source)

                            # Count leading dots
                            level = len(text) - len(text.lstrip("."))

                            module = text[level:]

                            break

                        elif child.type == "dotted_name":
                            # Absolute import:
                            #
                            # from pkg.sub.helpers import normalize
                            #
                            module = self._node_text(child, source)
                            break

                    base_module = self._resolve_relative_module(
                        current_package,
                        module,
                        level,
                    )

                    # ----------------------------------------------------------
                    # Resolve the imported module to a repository file.
                    #
                    # from .base import Base
                    #
                    # base_module = pkg.sub.base
                    # ----------------------------------------------------------
                    target = module_map.get(base_module)

                    if target is not None and target.entity_id != record.entity_id:
                        parsed.add_relation(Relation(
                            source_id=record.entity_id,
                            target_id=target.entity_id,
                            type=RelationType.IMPORTS,
                            metadata={
                                "resolved_via": "module_path_match",
                                "imported": base_module,
                                "relative_level": level,
                            },
                        ))

                    # ----------------------------------------------------------
                    # Record imported symbols as aliases.
                    # ----------------------------------------------------------
                    imported_names = self._extract_from_import_names(
                        node,
                        source,
                    )

                    for name, local in imported_names:
                        qualified = (
                            f"{base_module}.{name}"
                            if base_module
                            else name
                        )

                        aliases[local] = qualified

            self._imports_by_file[record.relative_path] = aliases

        def _extract_from_import_names(self, node, source: bytes):
            result = []

            for child in node.named_children:

                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")

                    if name_node is None:
                        continue

                    name = self._node_text(name_node, source)

                    local = (
                        self._node_text(alias_node, source)
                        if alias_node is not None
                        else name
                    )

                    result.append((name, local))

                elif child.type == "dotted_name":
                    name = self._node_text(child, source)

                    result.append((
                        name,
                        name.split(".")[-1],
                    ))

                elif child.type == "wildcard_import":
                    result.append(("*", "*"))

            return result

        @staticmethod
        def _resolve_relative_module(current_package: str, module: str, level: int) -> str:
            if level == 0:
                return module
            parts = current_package.split(".") if current_package else []
            strip = level - 1
            if strip <= len(parts):
                parts = parts[:len(parts) - strip]
            else:
                parts = []
            base = ".".join(parts)
            return f"{base}.{module}" if base and module else (base or module)

        def _import_statement_names(self, node, source: bytes):
            result = []
            for child in node.named_children:
                if child.type in {"dotted_name", "aliased_import"}:
                    if child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        alias_node = child.child_by_field_name("alias")
                        module = self._node_text(name_node, source)
                        local = self._node_text(alias_node, source) if alias_node else module.split(".")[0]
                    else:
                        module = self._node_text(child, source)
                        local = module.split(".")[0]
                    result.append({"module": module, "local": local})
            return result
