"""FastAPI interface for the GraphMem repository localizer.

Run with: uvicorn graphmem.api.main:app
"""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from graphmem.dataflow.analyzer import DataFlowSlicer, SliceDirection
from graphmem.ingestion.pipeline import RepositoryIngestor, RepositoryIndex
from graphmem.models.entities import EntityType
from graphmem.ranking.config import RankConfig, ablation_configs

app = FastAPI(title="GraphMem API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_registry: dict[str, RepositoryIndex] = {}
_registry_lock = RLock()
_ingestor = RepositoryIngestor()
_SAMPLE_PATH = Path(__file__).resolve().parents[3] / "examples" / "sample_repo"


class IndexRequest(BaseModel):
    path: str
    commit: str | None = None


class LocalizeRequest(BaseModel):
    repo_id: str = "sample"
    issue: str = Field(min_length=1)
    config: str = "full"
    top_k: int = Field(default=10, ge=1, le=100)


def _error(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": _status_name(status), "detail": detail})


def _status_name(status: int) -> str:
    return {400: "bad_request", 404: "not_found", 422: "validation_error", 500: "internal_error"}.get(status, "error")


@app.exception_handler(HTTPException)
async def http_error_handler(request, exc: HTTPException):
    from fastapi.responses import JSONResponse
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail and "detail" in detail:
        payload = detail
    else:
        payload = {"error": _status_name(exc.status_code), "detail": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)


def _get_repo(repo_id: str) -> RepositoryIndex:
    with _registry_lock:
        result = _registry.get(repo_id)
    if result is None:
        raise _error(404, f"Unknown repository: {repo_id}")
    return result


def _register(repo_id: str, result: RepositoryIndex) -> None:
    with _registry_lock:
        _registry[repo_id] = result


def _repo_id(path: str, commit: str | None = None) -> str:
    # A readable deterministic ID; callers can keep using it across requests.
    import hashlib
    resolved = str(Path(path).expanduser().resolve())
    suffix = f"@{commit}" if commit else ""
    return Path(resolved).name or hashlib.sha1((resolved + suffix).encode()).hexdigest()[:12]


@app.on_event("startup")
def load_sample_repository() -> None:
    if _SAMPLE_PATH.is_dir():
        try:
            _register("sample", _ingestor.ingest(str(_SAMPLE_PATH)))
        except Exception:
            # The API still starts when the optional bundled example is absent
            # or invalid; /repos reports no registered sample in that case.
            pass


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "graphmem"}


@app.get("/configs")
def configs() -> dict[str, Any]:
    return {
        "configs": [
            {"name": name, "weights": dict(config.weights)}
            for name, config in ablation_configs().items()
        ]
    }


@app.get("/repos")
def repos() -> dict[str, Any]:
    with _registry_lock:
        items = list(_registry.items())
    return {"repos": [
        {
            "repo_id": repo_id,
            "path": result.repository_path,
            "entities": len(result.parsed.entities),
            "relations": len(result.parsed.relations),
        }
        for repo_id, result in items
    ]}


@app.post("/repos/index")
def index_repository(request: IndexRequest) -> dict[str, Any]:
    path = Path(request.path).expanduser().resolve()
    if not path.exists():
        raise _error(404, f"Repository path does not exist: {path}")
    if not path.is_dir():
        raise _error(400, f"Repository path is not a directory: {path}")
    try:
        result = _ingestor.ingest(str(path))
    except (ValueError, NotADirectoryError) as exc:
        raise _error(400, str(exc)) from exc
    except Exception as exc:
        raise _error(500, f"Failed to index repository: {exc}") from exc
    repo_id = _repo_id(str(path), request.commit)
    _register(repo_id, result)
    return {
        "repo_id": repo_id,
        "path": result.repository_path,
        "entities": len(result.parsed.entities),
        "relations": len(result.parsed.relations),
    }


@app.post("/localize")
def localize(request: LocalizeRequest) -> dict[str, Any]:
    result = _get_repo(request.repo_id)
    available = ablation_configs()
    if request.config not in available:
        raise _error(422, f"Unknown config '{request.config}'. Available configs: {', '.join(available)}")
    try:
        localization = result.localizer.localize(
            request.issue, top_k=request.top_k, config=available[request.config]
        )
        # Frozen contract: do not wrap or mutate LocalizationResult.to_dict().
        return localization.to_dict()
    except Exception as exc:
        raise _error(500, f"Localization failed: {exc}") from exc


@app.get("/code")
def get_code(
    repo_id: str = Query(default="sample"),
    path: str = Query(..., description="Repository-relative source path"),
    start_line: int = Query(default=1, ge=1),
    end_line: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    result = _get_repo(repo_id)
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise _error(400, "path must be repository-relative and cannot traverse outside the repository")
    source_path = (Path(result.repository_path) / relative).resolve()
    root = Path(result.repository_path).resolve()
    if not source_path.is_relative_to(root):
        raise _error(400, "path must remain inside the repository")
    if not source_path.is_file():
        raise _error(404, f"Source file not found: {path}")
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise _error(400, "Source file is not UTF-8 text") from exc
    last = min(end_line or len(lines), len(lines))
    if last < start_line:
        raise _error(400, "end_line must be greater than or equal to start_line")
    return {
        "repo_id": repo_id, "path": relative.as_posix(),
        "start_line": start_line, "end_line": last,
        "total_lines": len(lines),
        "code": "\n".join(lines[start_line - 1:last]),
        "lines": [{"line": n, "code": lines[n - 1]} for n in range(start_line, last + 1)],
    }


@app.get("/graph/neighborhood")
def graph_neighborhood(
    repo_id: str = Query(default="sample"),
    entity_id: str | None = None,
    path: str | None = None,
    name: str | None = None,
    hops: int = Query(default=1, ge=0, le=3),
    limit: int = Query(default=60, ge=1, le=60),
) -> dict[str, Any]:
    result = _get_repo(repo_id)
    graph = result.graph
    entities = result.parsed.entities
    seed = graph.get_entity(entity_id) if entity_id else None
    if seed is None and (path or name):
        matches = [
            e for e in entities
            if (path is None or e.path == path)
            and (name is None or name.lower() in (e.qualified_name or e.name).lower())
        ]
        seed = matches[0] if matches else None
    if seed is None:
        raise _error(404, "No matching graph entity found; provide a valid entity_id, path, or name")
    visited = {seed.id}
    frontier = {seed.id}
    edge_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for _ in range(hops):
        next_frontier = set()
        for current in frontier:
            for target, rel, meta in graph.out_edges(current):
                edge_rows[(current, target.id, rel.value)] = {"source": current, "target": target.id, "type": rel.value, "metadata": meta}
                if target.id not in visited:
                    next_frontier.add(target.id)
            for source, rel, meta in graph.in_edges(current):
                edge_rows[(source.id, current, rel.value)] = {"source": source.id, "target": current, "type": rel.value, "metadata": meta}
                if source.id not in visited:
                    next_frontier.add(source.id)
        visited.update(next_frontier)
        frontier = next_frontier
        if len(visited) >= limit:
            break
    # Always include seed; cap nodes and return only edges whose endpoints survived.
    selected = [seed.id] + [eid for eid in sorted(visited) if eid != seed.id]
    selected = selected[:limit]
    selected_set = set(selected)
    nodes = []
    for eid in selected:
        e = graph.get_entity(eid)
        if e:
            nodes.append({
                "id": e.id, "type": e.type.value, "name": e.name,
                "qualified_name": e.qualified_name, "path": e.path,
                "start_line": e.start_line, "end_line": e.end_line,
            })
    edges = [edge for edge in edge_rows.values() if edge["source"] in selected_set and edge["target"] in selected_set]
    return {"repo_id": repo_id, "seed": seed.id, "nodes": nodes, "edges": edges}


@app.get("/slice")
def get_slice(
    repo_id: str = Query(default="sample"),
    path: str = Query(...),
    line: int = Query(..., ge=1),
    variable: str | None = None,
    direction: SliceDirection = SliceDirection.BOTH,
    max_depth: int = Query(default=10, ge=0, le=100),
) -> dict[str, Any]:
    result = _get_repo(repo_id)
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise _error(400, "path must be repository-relative")
    slicer = DataFlowSlicer(result.graph)
    sliced = slicer.slice_at(relative.as_posix(), line, direction=direction, variable=variable, max_depth=max_depth)
    if not sliced:
        raise _error(404, f"No statement found at {path}:{line}")
    return {
        "repo_id": repo_id, "path": relative.as_posix(), "line": line,
        "variable": variable, "direction": direction.value,
        "statements": [
            {
                "id": item.entity.id, "name": item.entity.name,
                "source": item.entity.metadata.get("source", item.entity.name),
                "path": item.entity.path, "start_line": item.entity.start_line,
                "end_line": item.entity.end_line, "depth": item.depth,
                "direction": item.direction, "variable": item.variable,
            }
            for item in sliced
        ],
    }
