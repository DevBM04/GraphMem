from graphmem.dataflow.analyzer import DataFlowSlicer, SliceDirection
from graphmem.graph.builder import GraphBuilder
from graphmem.parsing.python_parser import PythonParser
from graphmem.models.entities import EntityType
from graphmem.models.relations import RelationType

def build(tmp_path, source: str):
    (tmp_path / "m.py").write_text(source, encoding="utf-8")
    parsed = PythonParser().parse_repository(str(tmp_path))
    return DataFlowSlicer(GraphBuilder().build(parsed))


CHAIN = (
    "def f(x):\n"        # 1
    "    a = x\n"        # 2
    "    b = a + 1\n"    # 3
    "    c = 10\n"       # 4
    "    d = b * 2\n"    # 5
    "    return d\n"     # 6
)


def test_backward_slice_excludes_unrelated_statements(tmp_path):
    slicer = build(tmp_path, CHAIN)
    nodes = slicer.slice_at("m.py", 6, SliceDirection.BACKWARD)
    assert slicer.lines(nodes) == [2, 3, 5, 6]  # c (line 4) is irrelevant


def test_forward_slice(tmp_path):
    slicer = build(tmp_path, CHAIN)
    nodes = slicer.slice_at("m.py", 2, SliceDirection.FORWARD)
    assert slicer.lines(nodes) == [2, 3, 5, 6]


def test_bidirectional_slice(tmp_path):
    slicer = build(tmp_path, CHAIN)
    nodes = slicer.slice_at("m.py", 3, SliceDirection.BOTH)
    assert slicer.lines(nodes) == [2, 3, 5, 6]


def test_max_depth_limits_hops(tmp_path):
    slicer = build(tmp_path, CHAIN)
    nodes = slicer.slice_at("m.py", 6, SliceDirection.BACKWARD, max_depth=1)
    assert slicer.lines(nodes) == [5, 6]


def test_variable_filter_on_first_hop(tmp_path):
    slicer = build(
        tmp_path,
        "def g(x):\n"
        "    a = 1\n"
        "    b = 2\n"
        "    return a + b\n",
    )
    nodes = slicer.slice_at("m.py", 4, SliceDirection.BACKWARD, variable="a")
    assert slicer.lines(nodes) == [2, 4]


def test_tuple_assignment_keeps_both_variable_edges(tmp_path):
    slicer = build(
        tmp_path,
        "def h():\n"
    "    a, b = 1, 2\n"
        "    return a + b\n",
    )
    for var in ("a", "b"):
        nodes = slicer.slice_at("m.py", 3, SliceDirection.BACKWARD, variable=var)
        assert slicer.lines(nodes) == [2, 3], var

def test_if_header_uses_only_condition(tmp_path):
    (tmp_path / "m.py").write_text(
        "def example(x):\n"
        "    if x > 0:\n"
        "        print(body_only)\n",
        encoding="utf-8",
    )

    parsed = PythonParser().parse_repository(str(tmp_path))

    if_statement = next(
        entity
        for entity in parsed.entities_in_file("m.py")
        if entity.type == EntityType.STATEMENT
        and entity.start_line == 2
    )

    assert if_statement.metadata["uses"] == ["x"]
    assert "body_only" not in if_statement.metadata["uses"]


def test_body_statement_reaches_earlier_definition(tmp_path):
    slicer = build(
        tmp_path,
        "def example():\n"
        "    x = 10\n"
        "    if x > 0:\n"
        "        print(x)\n",
    )

    # The body use of x should retain its dependency on x = 10.
    nodes = slicer.slice_at("m.py", 4, SliceDirection.BACKWARD)

    assert 2 in slicer.lines(nodes)
    assert 4 in slicer.lines(nodes)


def test_with_statement_defines_as_target(tmp_path):
    (tmp_path / "m.py").write_text(
        "def example(path):\n"
        "    with open(path) as handle:\n"
        "        print(handle)\n",
        encoding="utf-8",
    )

    parsed = PythonParser().parse_repository(str(tmp_path))

    with_statement = next(
        entity
        for entity in parsed.entities_in_file("m.py")
        if entity.type == EntityType.STATEMENT
        and entity.start_line == 2
    )

    assert "path" in with_statement.metadata["uses"]
    assert "handle" in with_statement.metadata["defines"]