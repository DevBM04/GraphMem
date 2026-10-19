import pytest

from graphmem.evaluation.metrics import (
    candidate_coverage,
    hit_at_k,
    line_hit_at_k,
    mean,
    reciprocal_rank,
    recall_at_k,
)


def test_hit_at_k_gold_at_rank_1():
    ranked = ["A", "B", "C"]
    gold = {"A"}

    assert hit_at_k(ranked, gold, 1) == 1.0


def test_hit_at_k_gold_at_rank_3():
    ranked = ["A", "B", "C"]
    gold = {"C"}

    assert hit_at_k(ranked, gold, 3) == 1.0


def test_hit_at_k_gold_not_present():
    ranked = ["A", "B", "C"]
    gold = {"D"}

    assert hit_at_k(ranked, gold, 3) == 0.0


def test_recall_multiple_gold_items():
    ranked = ["A", "B", "C", "D"]
    gold = {"B", "D"}

    assert recall_at_k(ranked, gold, 3) == 0.5


def test_recall_all_gold_items():
    ranked = ["A", "B", "C"]
    gold = {"B", "C"}

    assert recall_at_k(ranked, gold, 3) == 1.0


def test_reciprocal_rank_gold_at_rank_1():
    ranked = ["A", "B", "C"]
    gold = {"A"}

    assert reciprocal_rank(ranked, gold) == 1.0


def test_reciprocal_rank_gold_at_rank_3():
    ranked = ["A", "B", "C"]
    gold = {"C"}

    assert reciprocal_rank(ranked, gold) == 1.0 / 3.0


def test_reciprocal_rank_gold_not_present():
    ranked = ["A", "B", "C"]
    gold = {"D"}

    assert reciprocal_rank(ranked, gold) == 0.0


def test_candidate_coverage():
    ranked = ["A", "B", "C"]
    gold = {"B", "C", "D"}

    assert candidate_coverage(ranked, gold) == 2.0 / 3.0


def test_duplicates_are_ignored():
    ranked = ["A", "A", "B", "B", "C"]
    gold = {"C"}

    assert reciprocal_rank(ranked, gold) == 1.0 / 3.0
    assert hit_at_k(ranked, gold, 3) == 1.0


def test_k_larger_than_list():
    ranked = ["A", "B"]
    gold = {"B"}

    assert hit_at_k(ranked, gold, 10) == 1.0
    assert recall_at_k(ranked, gold, 10) == 1.0


def test_empty_ranked_list():
    ranked = []
    gold = {"A"}

    assert hit_at_k(ranked, gold, 5) == 0.0
    assert recall_at_k(ranked, gold, 5) == 0.0
    assert reciprocal_rank(ranked, gold) == 0.0
    assert candidate_coverage(ranked, gold) == 0.0


def test_empty_gold_raises():
    ranked = ["A", "B"]

    with pytest.raises(ValueError, match="empty gold"):
        hit_at_k(ranked, set(), 1)

    with pytest.raises(ValueError, match="empty gold"):
        recall_at_k(ranked, set(), 1)

    with pytest.raises(ValueError, match="empty gold"):
        reciprocal_rank(ranked, set())

    with pytest.raises(ValueError, match="empty gold"):
        candidate_coverage(ranked, set())


def test_line_overlap():
    ranked_spans = [
        ("flask/app.py", 20, 30),
    ]
    gold_lines = {
        "flask/app.py": {25},
    }

    assert line_hit_at_k(ranked_spans, gold_lines, 1) == 1.0


def test_line_tolerance_edge():
    ranked_spans = [
        ("flask/app.py", 20, 30),
    ]
    gold_lines = {
        "flask/app.py": {32},
    }

    assert line_hit_at_k(ranked_spans, gold_lines, 1, tolerance=1) == 0.0
    assert line_hit_at_k(ranked_spans, gold_lines, 1, tolerance=2) == 1.0


def test_line_span_in_wrong_file():
    ranked_spans = [
        ("wrong.py", 20, 30),
    ]
    gold_lines = {
        "correct.py": {25},
    }

    assert line_hit_at_k(ranked_spans, gold_lines, 1) == 0.0


def test_line_hit_only_top_k():
    ranked_spans = [
        ("wrong.py", 1, 5),
        ("flask/app.py", 20, 30),
    ]
    gold_lines = {
        "flask/app.py": {25},
    }

    assert line_hit_at_k(ranked_spans, gold_lines, 1) == 0.0
    assert line_hit_at_k(ranked_spans, gold_lines, 2) == 1.0


def test_mean():
    assert mean([1.0, 0.5, 0.0]) == 0.5
    assert mean([]) == 0.0


def test_line_hit_with_empty_gold_lines():
    ranked_spans = [
        ("flask/app.py", 20, 30),
    ]
    gold_lines = {}

    assert line_hit_at_k(ranked_spans, gold_lines, 1) == 0.0
