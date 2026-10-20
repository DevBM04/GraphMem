import json

from graphmem.agent.tools import ToolRegistry
from graphmem.graph.builder import GraphBuilder
from graphmem.parsing.python_parser import PythonParser
from graphmem.retrieval.localizer import Localizer


def make_registry(tmp_path):
    (tmp_path / "auth.py").write_text(
        "def hash_password(raw):\n"
        "    salt = 'x'\n"
        "    return raw + salt\n"
        "\n"
        "def login(user, raw):\n"
        "    hashed = hash_password(raw)\n"
        "    return hashed == user.password\n",
        encoding="utf-8",
    )
    (tmp_path / "calc.py").write_text(
        "def compute(x):\n"
        "    base = x * 2\n"
        "    tax = base * 0.2\n"
        "    total = base + tax\n"
        "    return total\n",
        encoding="utf-8",
    )
    parsed = PythonParser().parse_repository(str(tmp_path))
    localizer = Localizer(GraphBuilder().build(parsed))
    return ToolRegistry(localizer, tmp_path), localizer


def test_search_entities(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("search_entities", query="login", limit=5)
    assert result["ok"] and result["results"]
    assert any(item["name"] == "login" for item in result["results"])


def test_traverse_graph(tmp_path):
    registry, localizer = make_registry(tmp_path)
    entity = next(e for e in localizer.graph.get_entities_by_type(__import__("graphmem.models.entities", fromlist=["EntityType"]).EntityType.FUNCTION) if e.name == "login")
    result = registry.call("traverse_graph", entity_id=entity.id, direction="both", hops=2)
    assert result["ok"] and result["nodes"][0]["id"] == entity.id
    assert len(result["nodes"]) <= 50


def test_get_code_span(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("get_code_span", path="auth.py", start=1, end=999)
    assert result["ok"] and "def hash_password" in result["code"]
    assert len(result["code"].splitlines()) <= 120


def test_get_entity_info(tmp_path):
    registry, localizer = make_registry(tmp_path)
    entity = localizer.index.by_name["login"][0]
    result = registry.call("get_entity_info", entity_id=entity.id)
    assert result["ok"] and result["entity"]["name"] == "login"


def test_get_dataflow_slice(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("get_dataflow_slice", path="calc.py", line=3, variable="base", direction="backward")
    assert result["ok"]
    assert isinstance(result["slice"], list)


def test_search_artifacts_absent_provider(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("search_artifacts", query="login bug")
    assert result["ok"] and result["results"] == [] and "No artifact provider" in result["note"]


def test_search_history_absent_provider(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("search_history", query="login bug")
    assert result["ok"] and result["results"] == [] and "No history provider" in result["note"]


def test_rank_suspect_regions(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("rank_suspect_regions", issue="login password hash is wrong", top_k=3)
    assert result["ok"] and "candidates" in result
    assert len(result["candidates"]) <= 3


def test_specs_are_valid_json_schema(tmp_path):
    registry, _ = make_registry(tmp_path)
    specs = registry.specs()
    assert len(specs) == 9
    json.dumps(specs)
    for spec in specs:
        schema = spec["parameters"]
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        assert set(schema["required"]) <= set(schema["properties"])


def test_dispatch_errors_are_returned(tmp_path):
    registry, _ = make_registry(tmp_path)
    assert registry.call("not_a_tool")["ok"] is False
    assert registry.call("get_entity_info", entity_id="missing")["ok"] is False


def test_code_span_blocks_path_traversal(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("get_code_span", path="../outside.txt", start=1, end=1)
    assert result["ok"] is False


def test_context_bundle_delegates_when_unavailable(tmp_path):
    registry, _ = make_registry(tmp_path)
    result = registry.call("build_context_bundle", issue="login is broken")
    assert result["ok"] and result["bundle"] is None
    assert "not registered" in result["note"]
