"""Main orchestration class for GraphMem's Tree-sitter Python parser."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional
from tree_sitter import Language, Parser
import tree_sitter_python as tree_sitter_python

from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.base import LanguageParser
from graphmem.parsing.common.entity_builder import _FileRecord, _ParsedFile, _Scope
from graphmem.parsing.common.source_utils import DEFAULT_EXCLUDED_DIRS
from graphmem.parsing.python.discovery import DiscoveryMixin
from graphmem.parsing.python.entities import EntityExtractionMixin
from graphmem.parsing.python.statements import StatementMixin
from graphmem.parsing.python.imports import ImportMixin
from graphmem.parsing.python.references import ReferenceMixin
from graphmem.parsing.python.inheritance import InheritanceMixin
from graphmem.parsing.python.calls import CallResolutionMixin
from graphmem.parsing.python.dataflow import DataFlowMixin


class PythonParser(
    DiscoveryMixin,
    EntityExtractionMixin,
    StatementMixin,
    ImportMixin,
    ReferenceMixin,
    InheritanceMixin,
    CallResolutionMixin,
    DataFlowMixin,
    LanguageParser,
):
    """Parse Python repositories into GraphMem's shared entity/relation schema."""

    language = "python"

    def __init__(self, excluded_dirs: Optional[set[str]] = None) -> None:
        self.excluded_dirs = (
            set(excluded_dirs)
            if excluded_dirs is not None
            else set(DEFAULT_EXCLUDED_DIRS)
        )

        # Tree-sitter grammar.  Keep this parser object reusable.
        self._language = Language(tree_sitter_python.language())
        self._parser = self._new_parser()

        self._parsed_files: list[_ParsedFile] = []
        self._entities_by_qualified_name: dict[str, CodeEntity] = {}
        self._entities_by_file_and_name: dict[tuple[str, str], CodeEntity] = {}
        self._entities_by_module_and_name: dict[tuple[str, str], CodeEntity] = {}

        # Import aliases per file, e.g.:
        #   from pkg.foo import bar as baz  -> baz: pkg.foo.bar
        self._imports_by_file: dict[str, dict[str, str]] = {}

    def parse_repository(self, repository_path: str) -> ParsedRepository:
        repo_root = Path(repository_path).resolve()
        if not repo_root.is_dir():
            raise NotADirectoryError(str(repo_root))

        repo_name = self.resolve_repo_name(str(repo_root))
        version = self.resolve_version(str(repo_root))
        parsed = ParsedRepository(repository_path=str(repo_root))

        repo_entity_id = f"repo://{repo_name}@{version}"
        parsed.add_entity(CodeEntity(
            id=repo_entity_id,
            type=EntityType.REPOSITORY,
            name=repo_name,
            metadata={"language": self.language, "version": version},
        ))

        file_records = self._discover_files(repo_root, repo_name, version)
        module_map = {r.module_name: r for r in file_records}

        self._build_directory_hierarchy(
            parsed=parsed,
            repo_name=repo_name,
            repo_entity_id=repo_entity_id,
            version=version,
            file_records=file_records,
        )

        for record in file_records:
            parsed.add_entity(CodeEntity(
                id=record.entity_id,
                type=EntityType.FILE,
                name=PurePosixPath(record.relative_path).name,
                path=record.relative_path,
                qualified_name=record.module_name,
                metadata={
                    "language": self.language,
                    "version": version,
                    "parser": "tree-sitter",
                    "imports": [],
                },
            ))

        self._parsed_files = []
        self._imports_by_file = {}

        # Pass 1: parse + entities + statements + imports.
        for record in file_records:
            self._parse_file(
                record=record,
                repo_name=repo_name,
                version=version,
                module_map=module_map,
                parsed=parsed,
            )

        # Pass 2: build symbol indexes once all entities exist.
        self._build_symbol_indexes(parsed)

        # Pass 3: class inheritance and non-call symbol references.
        self._resolve_inheritance(parsed)
        self._resolve_references(parsed)

        # Pass 4: calls.
        self._resolve_calls(parsed)

        # Pass 5: DEF/USE + data-flow.
        self._build_dataflow(parsed)

        return parsed

    def _new_parser(self) -> Parser:
        parser = Parser()
        # tree-sitter >= 0.22 supports Parser(language) while some versions
        # expose Parser() + parser.language.  Supporting both keeps the
        # adapter easier to install across environments.
        try:
            parser.language = self._language
        except Exception:
            try:
                parser.set_language(self._language)
            except AttributeError:
                parser = Parser(self._language)
        return parser
