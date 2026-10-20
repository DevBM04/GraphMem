"""Deterministic, bounded tools exposed to GraphMem's repository agent.

The module intentionally contains no LLM calls. It adapts GraphMem's existing
indexes, graph, data-flow slicer, evidence providers, and localizer to a small
JSON-serializable tool API.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Callable, Mapping

from graphmem.dataflow.analyzer import SliceDirection
from graphmem.models.entities import CodeEntity
from graphmem.models.relations import RelationType
from graphmem.ranking.config import RankConfig


MAX_TRAVERSAL_NODES = 50
MAX_CODE_LINES = 120
MAX_RESULTS = 100
MAX_OUTPUT_CHARS = 20_000


def _entity_dict(entity: CodeEntity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "type": entity.type.value,
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "path": entity.path,
        "start_line": entity.start_line,
        "end_line": entity.end_line,
        "parent_id": entity.parent_id,
    }


def _json_safe(value: Any) -> Any:
    """Convert GraphMem/dataclass/enum values to JSON-compatible primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value") and isinstance(value.value, (str, int, float, bool)):
        return value.value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _bounded_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep outputs serializable and bounded while preserving the result envelope."""
    safe = _json_safe(payload)
    encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= MAX_OUTPUT_CHARS:
        return safe
    # First trim common collection fields, then cap long strings if needed.
    for key in ("results", "entities", "nodes", "slice", "commits", "artifacts", "candidates", "scopes", "files"):
        items = safe.get(key)
        if isinstance(items, list):
            while items and len(json.dumps(safe, ensure_ascii=False, separators=(",", ":"))) > MAX_OUTPUT_CHARS:
                items.pop()
            if len(json.dumps(safe, ensure_ascii=False, separators=(",", ":"))) <= MAX_OUTPUT_CHARS:
                safe["truncated"] = True
                return safe
    for key, value in list(safe.items()):
        if isinstance(value, str) and len(value) > 1000:
            safe[key] = value[:1000] + "…"
    encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > MAX_OUTPUT_CHARS:
        return {"ok": bool(safe.get("ok")), "error": "Output exceeded the configured size limit", "truncated": True}
    return safe


def _success(**payload: Any) -> dict[str, Any]:
    return _bounded_result({"ok": True, **payload})


def _failure(message: str, **payload: Any) -> dict[str, Any]:
    return _bounded_result({"ok": False, "error": message, **payload})


class ToolRegistry:
    """Registry/dispatcher for deterministic repository-analysis tools."""

    def __init__(self, localizer: Any, repo_root: str | Path, providers: Any = None) -> None:
        self.localizer = localizer
        self.repo_root = Path(repo_root).resolve()
        self.providers = providers if providers is not None else getattr(localizer, "providers", [])
        if isinstance(self.providers, Mapping):
            self._providers = dict(self.providers)
        else:
            self._providers = {}
            for provider in self.providers or []:
                name = getattr(provider, "name", None) or getattr(provider, "signal", None) or provider.__class__.__name__.lower()
                self._providers[str(name).lower()] = provider
        self._tools: dict[str, Callable[..., dict[str, Any]]] = {
            "search_entities": self.search_entities,
            "traverse_graph": self.traverse_graph,
            "get_code_span": self.get_code_span,
            "get_entity_info": self.get_entity_info,
            "get_dataflow_slice": self.get_dataflow_slice,
            "search_artifacts": self.search_artifacts,
            "search_history": self.search_history,
            "rank_suspect_regions": self.rank_suspect_regions,
            "build_context_bundle": self.build_context_bundle,
        }
        self._schemas = {
            "search_entities": ("Search code entities by name, path, or lexical relevance.", {
                "type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}},
                "required": ["query"], "additionalProperties": False}),
            "traverse_graph": ("Traverse typed graph relationships from an entity using bounded breadth-first search.", {
                "type": "object", "properties": {"entity_id": {"type": "string"}, "direction": {"type": "string", "enum": ["out", "in", "both"]},
                "hops": {"type": "integer", "minimum": 0, "maximum": 10}, "edge_types": {"type": "array", "items": {"type": "string"}}},
                "required": ["entity_id"], "additionalProperties": False}),
            "get_code_span": ("Read a bounded source-code line range from the checked-out repository.", {
                "type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer", "minimum": 1}, "end": {"type": "integer", "minimum": 1}},
                "required": ["path", "start", "end"], "additionalProperties": False}),
            "get_entity_info": ("Return metadata for a code graph entity.", {
                "type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"], "additionalProperties": False}),
            "get_dataflow_slice": ("Return a bounded backward, forward, or bidirectional slice for a variable at a source line.", {
                "type": "object", "properties": {"path": {"type": "string"}, "line": {"type": "integer", "minimum": 1}, "variable": {"type": "string"},
                "direction": {"type": "string", "enum": ["backward", "forward", "both"]}},
                "required": ["path", "line", "variable"], "additionalProperties": False}),
            "search_artifacts": ("Search registered issue/pull-request artifact providers.", {
                "type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}},
                "required": ["query"], "additionalProperties": False}),
            "search_history": ("Search registered commit/history providers.", {
                "type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}},
                "required": ["query"], "additionalProperties": False}),
            "rank_suspect_regions": ("Rank suspicious repository regions for an issue.", {
                "type": "object", "properties": {"issue": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}, "config": {"type": ["object", "null"]}},
                "required": ["issue"], "additionalProperties": False}),
            "build_context_bundle": ("Build a bounded context bundle using the context builder supplied by C07.", {
                "type": "object", "properties": {"issue": {"type": "string"}, "seed_entities": {"type": "array", "items": {"type": "string"}}, "token_budget": {"type": "integer", "minimum": 1, "maximum": 100000}, "dataflow": {"type": ["array", "null"]}},
                "required": ["issue"], "additionalProperties": False}),
        }

    def specs(self) -> list[dict[str, Any]]:
        """Return LLM-friendly tool specs, each with a valid JSON Schema."""
        return [
            {"name": name, "description": description, "parameters": _json_safe(schema)}
            for name, (description, schema) in self._schemas.items()
        ]

    def call(self, name: str, **args: Any) -> dict[str, Any]:
        """Dispatch a tool call. Tool errors are converted to results, not raised."""
        tool = self._tools.get(name)
        if tool is None:
            return _failure(f"Unknown tool: {name}", available_tools=sorted(self._tools))
        try:
            return tool(**args)
        except Exception as exc:  # keep failures out of the LLM loop
            return _failure(f"{type(exc).__name__}: {exc}")

    def search_entities(self, query: str, limit: int = 10) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            return _failure("query must be a non-empty string", results=[])
        limit = max(1, min(int(limit), MAX_RESULTS))
        index = self.localizer.index
        hits = index.search_scopes(query.split(), limit)
        by_id = {entity.id: (entity, float(score)) for entity, score in hits}
        # Exact identifier/name matches should rank first even if BM25 misses them.
        for entity in index.by_name.get(query.strip(), []):
            by_id[entity.id] = (entity, max(1.0, by_id.get(entity.id, (entity, 0.0))[1]))
        results = [
            {**_entity_dict(entity), "score": round(score, 4)}
            for entity, score in sorted(by_id.values(), key=lambda item: (-item[1], item[0].id))[:limit]
        ]
        return _success(results=results, count=len(results), query=query)

    def traverse_graph(
        self, entity_id: str, direction: str = "both", hops: int = 2,
        edge_types: list[str] | None = None,
    ) -> dict[str, Any]:
        if direction not in {"out", "in", "both"}:
            return _failure("direction must be one of: out, in, both", nodes=[])
        hops = max(0, min(int(hops), 10))
        graph = self.localizer.graph
        seed = graph.get_entity(entity_id)
        if seed is None:
            return _failure(f"Unknown entity ID: {entity_id}", nodes=[])
        allowed = None
        if edge_types is not None:
            try:
                allowed = {RelationType(v.lower()) for v in edge_types}
            except ValueError as exc:
                return _failure(f"Unknown edge type: {exc}", nodes=[])
        queue = deque([(seed, 0, [seed.id])])
        visited = {seed.id}
        nodes, edges = [], []
        while queue and len(nodes) < MAX_TRAVERSAL_NODES:
            entity, depth, path = queue.popleft()
            nodes.append({**_entity_dict(entity), "depth": depth, "path": path})
            if depth >= hops:
                continue
            adjacent = []
            if direction in {"out", "both"}:
                adjacent.extend((n, rel, meta, "out") for n, rel, meta in graph.out_edges(entity.id))
            if direction in {"in", "both"}:
                adjacent.extend((n, rel, meta, "in") for n, rel, meta in graph.in_edges(entity.id))
            adjacent.sort(key=lambda x: (x[3], x[1].value, x[0].id))
            for neighbor, rel, meta, orient in adjacent:
                if allowed is not None and rel not in allowed:
                    continue
                edges.append({"source": entity.id if orient == "out" else neighbor.id,
                              "target": neighbor.id if orient == "out" else entity.id,
                              "type": rel.value, "direction": orient})
                if neighbor.id not in visited and len(visited) < MAX_TRAVERSAL_NODES:
                    visited.add(neighbor.id)
                    queue.append((neighbor, depth + 1, path + [neighbor.id]))
        return _success(nodes=nodes[:MAX_TRAVERSAL_NODES], edges=edges[:MAX_TRAVERSAL_NODES * 4],
                        count=min(len(nodes), MAX_TRAVERSAL_NODES), truncated=bool(queue))

    def get_code_span(self, path: str, start: int, end: int) -> dict[str, Any]:
        if not isinstance(path, str) or not path:
            return _failure("path must be a non-empty string")
        if int(start) < 1 or int(end) < int(start):
            return _failure("start/end must be valid 1-based line numbers")
        start, end = int(start), min(int(end), int(start) + MAX_CODE_LINES - 1)
        target = (self.repo_root / path).resolve()
        try:
            target.relative_to(self.repo_root)
        except ValueError:
            return _failure("path must stay inside repo_root")
        if not target.is_file():
            return _failure(f"Source file not found: {path}")
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return _failure(f"Could not read source file: {exc}")
        if start > len(lines):
            return _failure(f"start line {start} exceeds file length {len(lines)}")
        actual_end = min(end, len(lines))
        return _success(path=target.relative_to(self.repo_root).as_posix(), start=start, end=actual_end,
                        code="\n".join(lines[start - 1:actual_end]), truncated=(actual_end < int(end) or actual_end - start + 1 >= MAX_CODE_LINES))

    def get_entity_info(self, entity_id: str) -> dict[str, Any]:
        entity = self.localizer.graph.get_entity(entity_id)
        if entity is None:
            return _failure(f"Unknown entity ID: {entity_id}")
        return _success(entity=_entity_dict(entity), metadata=_json_safe(entity.metadata))

    def get_dataflow_slice(self, path: str, line: int, variable: str, direction: str = "both") -> dict[str, Any]:
        try:
            slice_direction = SliceDirection(direction.lower())
        except (ValueError, AttributeError):
            return _failure("direction must be backward, forward, or both", slice=[])
        if int(line) < 1:
            return _failure("line must be >= 1", slice=[])
        # Normalize path to the same repo-relative form used by graph entities.
        normalized = path.replace("\\", "/").lstrip("./")
        slicer = self.localizer.slicer
        nodes = slicer.slice_at(normalized, int(line), slice_direction, variable=variable, max_depth=50)
        if not nodes:
            return _success(slice=[], note="No data-flow slice found for this path/line/variable.")
        out = []
        seed = slicer.statement_at(normalized, int(line))
        if seed is not None:
            out.append({"entity": _entity_dict(seed), "depth": 0, "direction": None, "variable": variable})
        for node in nodes[:MAX_TRAVERSAL_NODES]:
            out.append({"entity": _entity_dict(node.entity), "depth": node.depth, "direction": node.direction, "variable": node.variable})
        return _success(slice=out, count=len(out), truncated=len(nodes) > MAX_TRAVERSAL_NODES)

    def search_artifacts(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._search_provider("artifact", query, limit)

    def search_history(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._search_provider("history", query, limit)

    def _search_provider(self, kind: str, query: str, limit: int) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            return _failure("query must be a non-empty string", results=[])
        limit = max(1, min(int(limit), MAX_RESULTS))
        candidates = [p for key, p in self._providers.items() if kind in key.lower()]
        # HistoryProvider currently contributes ranking evidence rather than exposing
        # a search method; offer a deterministic search over its cached commits.
        if kind == "history":
            for p in self._providers.values():
                if hasattr(p, "commits") and p not in candidates:
                    candidates.append(p)
        if not candidates:
            return _success(results=[], count=0, note=f"No {kind} provider is registered.")
        results = []
        for provider in candidates:
            method = next((getattr(provider, method_name, None) for method_name in
                           (("search", "search_artifacts", "find_artifacts") if kind == "artifact"
                            else ("search", "search_history", "find_commits")) if callable(getattr(provider, method_name, None))), None)
            if method is not None:
                try:
                    value = method(query, limit=limit)
                except TypeError:
                    value = method(query)
                if isinstance(value, list):
                    results.extend(_json_safe(value))
                elif value is not None:
                    results.append(_json_safe(value))
            elif kind == "history" and hasattr(provider, "commits"):
                terms = set(query.lower().split())
                for commit in provider.commits:
                    text = f"{getattr(commit, 'subject', '')} {' '.join(getattr(commit, 'files', ())) }".lower()
                    if all(term in text for term in terms):
                        results.append({"sha": commit.sha, "subject": commit.subject,
                                        "timestamp": commit.unix_time, "files": list(commit.files)})
                        if len(results) >= limit:
                            break
        return _success(results=results[:limit], count=min(len(results), limit),
                        note=None if results else f"No matching {kind} results.")

    def build_context_bundle(
        self, issue: str, seed_entities: list[str] | None = None,
        token_budget: int = 8000, dataflow: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Delegate context construction to the C07 implementation when registered."""
        if not isinstance(issue, str) or not issue.strip():
            return _failure("issue must be a non-empty string")
        token_budget = max(1, min(int(token_budget), 100000))
        builder = getattr(self.localizer, "build_context_bundle", None)
        if not callable(builder):
            for key, provider in self._providers.items():
                if "context" in key and callable(getattr(provider, "build_context_bundle", None)):
                    builder = provider.build_context_bundle
                    break
        if not callable(builder):
            return _success(bundle=None, note="Context builder from C07 is not registered.")
        try:
            result = builder(
                issue=issue,
                seed_entities=list(seed_entities or []),
                token_budget=token_budget,
                dataflow=dataflow,
            )
        except TypeError:
            # Accommodate the concrete C07 API if its parameter names differ.
            result = builder(issue, list(seed_entities or []), token_budget)
        return _success(bundle=_json_safe(result))

    def rank_suspect_regions(self, issue: str, top_k: int = 10, config: Any = None) -> dict[str, Any]:
        if not isinstance(issue, str) or not issue.strip():
            return _failure("issue must be a non-empty string", results=[])
        top_k = max(1, min(int(top_k), MAX_RESULTS))
        cfg = config
        if isinstance(cfg, dict):
            # Only accept known RankConfig fields; never instantiate arbitrary objects.
            try:
                cfg = RankConfig(**cfg)
            except (TypeError, ValueError) as exc:
                return _failure(f"Invalid rank config: {exc}")
        result = self.localizer.localize(issue, top_k=top_k, config=cfg)
        payload = result.to_dict(max_candidates=top_k)
        return _success(**payload)
