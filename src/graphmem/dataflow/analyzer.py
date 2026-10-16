"""Intra-procedural data-flow slicing over DATAFLOW_DEF_USE edges (ADR-05).

Edge direction in the graph is  definition statement -> use statement.

  backward slice: "what produced the value used here?"   (follow in-edges)
  forward slice:  "what does the value defined here affect?" (follow out-edges)
  both:           union of the two

Limitations (by design, MVP):
  * Intra-procedural only; inter-procedural flow goes through CALLS edges.
  * Function parameters have no defining statement, so slices stop there.
  * No control dependence (an `if` header is only included if it uses a
    sliced variable).
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum

from graphmem.graph.store import GraphStore
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import RelationType


class SliceDirection(str, Enum):
    BACKWARD = "backward"
    FORWARD = "forward"
    BOTH = "both"


@dataclass
class SliceNode:
    entity: CodeEntity
    depth: int                       # hops from the seed statement
    direction: str | None            # "backward" / "forward" / None for seed
    variable: str | None             # variable on the edge that reached it
    path: list[str] = field(default_factory=list)  # statement ids seed -> here

    @property
    def line(self) -> int | None:
        return self.entity.start_line


class DataFlowSlicer:
    def __init__(self, graph: GraphStore) -> None:
        self.graph = graph
        self._by_file: dict[str, list[CodeEntity]] = defaultdict(list)
        self._by_file_starts: dict[str, list[int]] = {}
        self._by_scope: dict[str, list[CodeEntity]] = defaultdict(list)
        self._build_index()

    # ------------------------------------------------------------------
    # Statement lookup
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        for stmt in self.graph.get_entities_by_type(EntityType.STATEMENT):
            if stmt.path:
                self._by_file[stmt.path].append(stmt)
            if stmt.parent_id:
                self._by_scope[stmt.parent_id].append(stmt)
        for path, statements in self._by_file.items():
            statements.sort(key=lambda s: (s.start_line or 0, s.end_line or 0))
            # Keep this parallel to _by_file[path] for bisect-based lookup.
            self._by_file_starts[path] = [s.start_line or 0 for s in statements]
        for statements in self._by_scope.values():
            statements.sort(key=lambda s: (s.start_line or 0, s.end_line or 0))

    def statement_at(self, path: str, line: int) -> CodeEntity | None:
        """Innermost statement covering `line` (smallest span wins)."""
        statements = self._by_file.get(path, [])
        starts = self._by_file_starts.get(path, [])
        # Only statements whose start line is <= the target can contain it.
        i = bisect_right(starts, line) - 1
        best: CodeEntity | None = None
        best_span: int | None = None
        best_index = -1

        while i >= 0:
            stmt = statements[i]
            start = stmt.start_line
            end = stmt.end_line

            # Earlier-starting statements cannot beat the current span once
            # the distance from their start to the target exceeds that span.
            # Use '>' rather than '>=' to preserve first-in-sort-order
            # tie-breaking for statements with equal spans.
            if best_span is not None and start is not None and line - start > best_span:
                break

            if start is not None and end is not None and start <= line <= end:
                span = end - start
                if (
                    best is None
                    or span < best_span
                    or (span == best_span and i < best_index)
                ):
                    best, best_span, best_index = stmt, span, i
            i -= 1

        return best

    def statements_in_scope(self, scope_id: str) -> list[CodeEntity]:
        """All statements whose enclosing scope is the given function/method."""
        return list(self._by_scope.get(scope_id, []))

    # ------------------------------------------------------------------
    # Slicing
    # ------------------------------------------------------------------

    def slice(
        self,
        seed: CodeEntity | str,
        direction: SliceDirection = SliceDirection.BOTH,
        variable: str | None = None,
        max_depth: int | None = None,
    ) -> list[SliceNode]:
        """Slice from a statement. The seed is always included at depth 0.

        `variable` restricts only the *first* hop (the variable of interest
        at the seed); later hops follow every dependency, which is what a
        standard slice does.
        """
        seed_entity = self.graph.get_entity(seed) if isinstance(seed, str) else seed
        if seed_entity is None:
            return []

        results = [SliceNode(seed_entity, 0, None, None, [seed_entity.id])]

        if direction in (SliceDirection.BACKWARD, SliceDirection.BOTH):
            results += self._walk(seed_entity, SliceDirection.BACKWARD, variable, max_depth)
        if direction in (SliceDirection.FORWARD, SliceDirection.BOTH):
            results += self._walk(seed_entity, SliceDirection.FORWARD, variable, max_depth)
        return results

    def slice_at(
        self,
        path: str,
        line: int,
        direction: SliceDirection = SliceDirection.BOTH,
        variable: str | None = None,
        max_depth: int | None = None,
    ) -> list[SliceNode]:
        seed = self.statement_at(path, line)
        if seed is None:
            return []
        return self.slice(seed, direction, variable, max_depth)

    def _walk(
        self,
        seed: CodeEntity,
        direction: SliceDirection,
        variable: str | None,
        max_depth: int | None,
    ) -> list[SliceNode]:
        edges_of = (
            self.graph.in_edges
            if direction == SliceDirection.BACKWARD
            else self.graph.out_edges
        )

        out: list[SliceNode] = []
        visited = {seed.id}
        queue = deque([(seed, 0, [seed.id])])

        while queue:
            current, depth, path = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue

            for neighbor, rel_type, meta in edges_of(current.id):
                if rel_type != RelationType.DATAFLOW_DEF_USE:
                    continue
                var = meta.get("variable")
                if depth == 0 and variable is not None and var != variable:
                    continue
                if neighbor.id in visited:
                    continue
                visited.add(neighbor.id)
                new_path = path + [neighbor.id]
                out.append(SliceNode(neighbor, depth + 1, direction.value, var, new_path))
                queue.append((neighbor, depth + 1, new_path))

        return out

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    @staticmethod
    def lines(slice_nodes: list[SliceNode]) -> list[int]:
        return sorted({n.line for n in slice_nodes if n.line is not None})