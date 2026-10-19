def _deduplicate(ranked: list[str]) -> list[str]:
    """Return ranked IDs with duplicates removed, keeping the first occurrence."""
    return list(dict.fromkeys(ranked))


def hit_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """Return 1.0 if any gold item appears in the top k ranked items, otherwise 0.0."""
    if not gold:
        raise ValueError("empty gold")

    ranked = _deduplicate(ranked)
    return 1.0 if any(item in gold for item in ranked[:k]) else 0.0


def recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """Return the fraction of gold items that appear in the top k ranked items."""
    if not gold:
        raise ValueError("empty gold")

    ranked = _deduplicate(ranked)
    found = sum(item in gold for item in ranked[:k])
    return found / len(gold)


def reciprocal_rank(ranked: list[str], gold: set[str]) -> float:
    """Return the reciprocal of the rank of the first gold item, or 0.0 if none is found."""
    if not gold:
        raise ValueError("empty gold")

    ranked = _deduplicate(ranked)

    for position, item in enumerate(ranked, start=1):
        if item in gold:
            return 1.0 / position

    return 0.0


def candidate_coverage(ranked: list[str], gold: set[str]) -> float:
    """Return the fraction of gold items that appear anywhere in the ranked candidates."""
    if not gold:
        raise ValueError("empty gold")

    ranked = _deduplicate(ranked)
    found = sum(item in gold for item in ranked)
    return found / len(gold)


def line_hit_at_k(
    ranked_spans: list[tuple[str, int, int]],
    gold_lines: dict[str, set[int]],
    k: int,
    tolerance: int = 0,
) -> float:
    """Return 1.0 if any top-k span overlaps a gold line within tolerance, otherwise 0.0."""
    for path, start_line, end_line in ranked_spans[:k]:
        if path not in gold_lines:
            continue

        for gold_line in gold_lines[path]:
            if start_line - tolerance <= gold_line <= end_line + tolerance:
                return 1.0

    return 0.0


def mean(values: list[float]) -> float:
    """Return the arithmetic mean of the values, or 0.0 for an empty list."""
    if not values:
        return 0.0

    return sum(values) / len(values)
