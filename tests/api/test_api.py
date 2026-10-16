from pathlib import Path

from fastapi.testclient import TestClient

from graphmem.api import main


client = TestClient(main.app)


def setup_function():
    main._registry.clear()
    main.load_sample_repository()


def test_health_and_configs():
    assert client.get("/health").json()["status"] == "ok"
    response = client.get("/configs")
    assert response.status_code == 200
    assert {item["name"] for item in response.json()["configs"]} == set(main.ablation_configs())


def test_sample_repo_is_loaded_and_localizes():
    repos = client.get("/repos").json()["repos"]
    assert any(repo["repo_id"] == "sample" for repo in repos)
    response = client.post("/localize", json={
        "repo_id": "sample", "issue": "broken function returns wrong value", "config": "full"
    })
    assert response.status_code == 200
    body = response.json()
    assert {"issue", "config", "files", "scopes", "candidates", "timings_ms"} <= body.keys()


def test_unknown_repo_and_config_return_structured_errors():
    response = client.post("/localize", json={
        "repo_id": "missing", "issue": "bug", "config": "full"
    })
    assert response.status_code == 404
    assert set(response.json()) == {"error", "detail"}

    response = client.post("/localize", json={
        "repo_id": "sample", "issue": "bug", "config": "not-a-config"
    })
    assert response.status_code == 422
    assert set(response.json()) == {"error", "detail"}


def test_index_code_and_neighborhood(tmp_path):
    repo = tmp_path / "tiny"
    repo.mkdir()
    (repo / "app.py").write_text("def calculate(value):\n    result = value + 1\n    return result\n", encoding="utf-8")
    response = client.post("/repos/index", json={"path": str(repo)})
    assert response.status_code == 200
    repo_id = response.json()["repo_id"]

    code = client.get("/code", params={"repo_id": repo_id, "path": "app.py"}).json()
    assert "return result" in code["code"]

    graph = client.get("/graph/neighborhood", params={"repo_id": repo_id, "path": "app.py", "hops": 1})
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) <= 60
    assert all("type" in edge for edge in graph.json()["edges"])


def test_slice_and_path_traversal_rejected(tmp_path):
    repo = tmp_path / "slice_repo"
    repo.mkdir()
    (repo / "app.py").write_text("def calculate(value):\n    result = value + 1\n    return result\n", encoding="utf-8")
    repo_id = client.post("/repos/index", json={"path": str(repo)}).json()["repo_id"]

    response = client.get("/slice", params={
        "repo_id": repo_id, "path": "app.py", "line": 3, "variable": "result", "direction": "backward"
    })
    assert response.status_code == 200
    assert response.json()["statements"]

    response = client.get("/code", params={"repo_id": repo_id, "path": "../outside.py"})
    assert response.status_code == 400


def test_cors_preflight():
    response = client.options("/health", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    })
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
