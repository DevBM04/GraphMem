from graphmem.dataflow.analyzer import DataFlowSlicer, SliceDirection
from graphmem.graph.builder import GraphBuilder
from graphmem.parsing.python_parser import PythonParser


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