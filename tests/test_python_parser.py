"""Tests for graphmem.parsing.python_parser.PythonParser.

Run with:  pytest tests/test_python_parser.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphmem.models.entities import EntityType
from graphmem.models.relations import RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing import PythonParser

SAMPLE_REPO = Path(__file__).resolve().parents[1] / "examples" / "sample_repo"


@pytest.fixture(scope="module")
def parsed() -> ParsedRepository:
    parser = PythonParser()
    return parser.parse_repository(str(SAMPLE_REPO))


# ----------------------------------------------------------------------
# Small local helpers (kept in the test file, not on the shared model -
# ParsedRepository only exposes add_entity/add_relation/get_entity).
# ----------------------------------------------------------------------


def entities_by_type(parsed_repo: ParsedRepository, entity_type: EntityType):
    return [e for e in parsed_repo.entities if e.type == entity_type]


def relations_by_type(parsed_repo: ParsedRepository, relation_type: RelationType):
    return [r for r in parsed_repo.relations if r.type == relation_type]


def find_one(parsed_repo: ParsedRepository, *, type: EntityType, qualified_name: str = None, path: str = None):
    matches = [
        e
        for e in parsed_repo.entities
        if e.type == type
        and (qualified_name is None or e.qualified_name == qualified_name)
        and (path is None or e.path == path)
    ]
    assert len(matches) == 1, f"expected exactly one match, got {len(matches)}: {matches}"
    return matches[0]


def children_of(parsed_repo: ParsedRepository, entity_id: str):
    child_ids = {
        r.target_id
        for r in parsed_repo.relations
        if r.type == RelationType.CONTAINS and r.source_id == entity_id
    }
    return [e for e in parsed_repo.entities if e.id in child_ids]


# ----------------------------------------------------------------------
# Basic shape of the output
# ----------------------------------------------------------------------


def test_returns_parsed_repository(parsed: ParsedRepository):
    assert isinstance(parsed, ParsedRepository)
    assert parsed.repository_path == str(SAMPLE_REPO)
    assert parsed.entities
    assert parsed.relations


def test_repository_and_file_entities_exist(parsed: ParsedRepository):
    repo_entities = entities_by_type(parsed, EntityType.REPOSITORY)
    assert len(repo_entities) == 1

    file_entities = entities_by_type(parsed, EntityType.FILE)
    file_paths = {e.path for e in file_entities}
    assert file_paths == {
        "file.py",
        "broken.py",
        "pkg/__init__.py",
        "pkg/sub/__init__.py",
        "pkg/sub/helpers.py",
        "pkg/sub/base.py",
    }


def test_directory_entities_exist(parsed: ParsedRepository):
    dir_paths = {e.path for e in entities_by_type(parsed, EntityType.DIRECTORY)}
    assert dir_paths == {"pkg", "pkg/sub"}


# ----------------------------------------------------------------------
# Matches the diagram in the task description:
#
# file.py
# ├── ClassA
# │    ├── method1()
# │    └── method2()
# │
# └── function1()
# ----------------------------------------------------------------------


def test_class_extracted(parsed: ParsedRepository):
    class_a = find_one(parsed, type=EntityType.CLASS, qualified_name="ClassA")
    assert class_a.name == "ClassA"
    assert class_a.path == "file.py"
    assert class_a.start_line == 15  # class ClassA: line in file.py


def test_methods_extracted_as_methods_not_functions(parsed: ParsedRepository):
    method1 = find_one(parsed, type=EntityType.METHOD, qualified_name="ClassA.method1")
    method2 = find_one(parsed, type=EntityType.METHOD, qualified_name="ClassA.method2")
    assert method1.name == "method1"
    assert method2.name == "method2"

    # These must NOT show up as top-level FUNCTION entities.
    function_names = {e.qualified_name for e in entities_by_type(parsed, EntityType.FUNCTION)}
    assert "method1" not in function_names
    assert "method2" not in function_names


def test_module_level_function_extracted(parsed: ParsedRepository):
    function1 = find_one(parsed, type=EntityType.FUNCTION, qualified_name="function1")
    assert function1.name == "function1"
    assert function1.path == "file.py"


def test_contains_hierarchy_file_to_class_to_methods(parsed: ParsedRepository):
    file_entity = find_one(parsed, type=EntityType.FILE, path="file.py")
    class_a = find_one(parsed, type=EntityType.CLASS, qualified_name="ClassA")
    method1 = find_one(parsed, type=EntityType.METHOD, qualified_name="ClassA.method1")
    method2 = find_one(parsed, type=EntityType.METHOD, qualified_name="ClassA.method2")
    function1 = find_one(parsed, type=EntityType.FUNCTION, qualified_name="function1")

    contains = relations_by_type(parsed, RelationType.CONTAINS)
    pairs = {(r.source_id, r.target_id) for r in contains}

    assert (file_entity.id, class_a.id) in pairs
    assert (class_a.id, method1.id) in pairs
    assert (class_a.id, method2.id) in pairs
    assert (file_entity.id, function1.id) in pairs

    # parent_id shortcut on the entity itself should agree with the edges.
    assert method1.parent_id == class_a.id
    assert function1.parent_id == file_entity.id


def test_children_of_helper_matches_contains_edges(parsed: ParsedRepository):
    class_a = find_one(parsed, type=EntityType.CLASS, qualified_name="ClassA")
    children = {c.qualified_name for c in children_of(parsed, class_a.id)}
    assert children == {"ClassA.method1", "ClassA.method2"}


# ----------------------------------------------------------------------
# Imports
# ----------------------------------------------------------------------


def test_absolute_import_resolved_within_repo(parsed: ParsedRepository):
    file_entity = find_one(parsed, type=EntityType.FILE, path="file.py")
    helpers_entity = find_one(parsed, type=EntityType.FILE, path="pkg/sub/helpers.py")

    imports = relations_by_type(parsed, RelationType.IMPORTS)
    pairs = {(r.source_id, r.target_id) for r in imports}
    assert (file_entity.id, helpers_entity.id) in pairs


def test_relative_import_resolved(parsed: ParsedRepository):
    helpers_entity = find_one(parsed, type=EntityType.FILE, path="pkg/sub/helpers.py")
    base_entity = find_one(parsed, type=EntityType.FILE, path="pkg/sub/base.py")

    imports = relations_by_type(parsed, RelationType.IMPORTS)
    pairs = {(r.source_id, r.target_id) for r in imports}
    assert (helpers_entity.id, base_entity.id) in pairs


def test_external_import_not_turned_into_an_edge_but_kept_as_metadata(parsed: ParsedRepository):
    file_entity = find_one(parsed, type=EntityType.FILE, path="file.py")

    # `import os` must not create an IMPORTS edge to anything (there's no
    # `os` entity in this repo), but the raw statement should be recorded.
    imports = relations_by_type(parsed, RelationType.IMPORTS)
    targets_from_file = {r.target_id for r in imports if r.source_id == file_entity.id}
    os_like_targets = [t for t in targets_from_file if t.endswith("/os@working") or "::os" in t]
    assert os_like_targets == []

    assert any("import os" in stmt for stmt in file_entity.metadata["imports"])


# ----------------------------------------------------------------------
# Robustness
# ----------------------------------------------------------------------


def test_syntax_error_does_not_crash_and_is_recorded(parsed: ParsedRepository):
    broken = find_one(parsed, type=EntityType.FILE, path="broken.py")

    assert "parse_errors" in broken.metadata
    assert broken.metadata["parse_errors"]


def test_nonexistent_repository_path_raises():
    parser = PythonParser()
    with pytest.raises(NotADirectoryError):
        parser.parse_repository("/definitely/does/not/exist/anywhere")


def test_stable_ids_follow_adr14_format(parsed: ParsedRepository):
    class_a = find_one(parsed, type=EntityType.CLASS, qualified_name="ClassA")
    # repo://<repo_name>/<relative_path>::<qualified_name>@<version>
    assert class_a.id.startswith("repo://")
    assert "/file.py::ClassA@" in class_a.id


def test_get_entity_lookup(parsed: ParsedRepository):
    file_entity = find_one(parsed, type=EntityType.FILE, path="file.py")
    assert parsed.get_entity(file_entity.id) is file_entity
    assert parsed.get_entity("repo://does-not-exist@working") is None

def test_deeply_nested_compound_statements_parse_without_recursion_error(tmp_path):
    depth = 150
    source = "def deeply_nested():\n"
    source += "".join("    " * (level + 1) + "if True:\n" for level in range(depth))
    source += "    " * (depth + 1) + "return 1\n"

    (tmp_path / "deep.py").write_text(source, encoding="utf-8")
    parsed = PythonParser().parse_repository(str(tmp_path))

    function = find_one(
        parsed,
        type=EntityType.FUNCTION,
        qualified_name="deeply_nested",
    )
    assert function is not None