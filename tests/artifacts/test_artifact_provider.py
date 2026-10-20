from datetime import datetime, timezone

from graphmem.artifacts.loader import load_artifacts
from graphmem.artifacts.models import Artifact
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.retrieval.providers.artifact import ArtifactProvider


def make_artifact(
    kind="pr",
    number=1,
    title="Fix invalid token handling",
    body="Correct the invalid token error in the parser.",
    created_at="2025-01-01T00:00:00+00:00",
    files=None,
):
    return Artifact(
        kind=kind,
        number=number,
        title=title,
        body=body,
        created_at=datetime.fromisoformat(created_at),
        files=files or [],
    )


def make_entity(
    entity_id="parser",
    name="parser",
    path="src/parser.py",
    qualified_name=None,
):
    return CodeEntity(
        id=entity_id,
        type=EntityType.FILE,
        name=name,
        path=path,
        qualified_name=qualified_name,
    )


def test_explicit_path_link():
    artifact = make_artifact(files=["src/parser.py"])
    provider = ArtifactProvider([artifact])

    result = provider.score(
        [make_entity()],
        "Fix invalid token handling in the parser",
    )

    assert "parser" in result
    evidence = result["parser"][0]

    assert evidence.type == "artifact"
    assert evidence.detail["artifact"] == "PR#1"
    assert evidence.detail["link"] == "explicit_path"
    assert evidence.detail["confidence"] == 1.0
    assert evidence.weight == 1.0


def test_entity_mention_link():
    artifact = make_artifact(
        title="Fix invalid token handling",
        body="The ParserEngine rejects invalid tokens.",
        files=["src/other.py"],
    )
    entity = make_entity(
        entity_id="engine",
        name="ParserEngine",
        path="src/parser_engine.py",
    )

    provider = ArtifactProvider([artifact])
    result = provider.score(
        [entity],
        "Fix invalid token handling in ParserEngine",
    )

    assert "engine" in result
    evidence = result["engine"][0]

    assert evidence.detail["link"] == "entity_mention"
    assert evidence.detail["confidence"] == 0.8
    assert evidence.weight == 0.8


def test_unrelated_scope_gets_no_evidence():
    artifact = make_artifact(
        title="Fix invalid token handling",
        body="The parser rejects invalid tokens.",
        files=["src/parser.py"],
    )
    unrelated = make_entity(
        entity_id="database",
        name="DatabaseManager",
        path="src/database.py",
    )

    provider = ArtifactProvider([artifact])
    result = provider.score(
        [unrelated],
        "Fix invalid token handling",
    )

    assert "database" not in result


def test_as_of_filters_future_pr():
    past = make_artifact(
        number=1,
        title="Fix invalid token parser",
        created_at="2024-01-01T00:00:00+00:00",
        files=["src/parser.py"],
    )
    future = make_artifact(
        number=2,
        title="Fix invalid token parser",
        created_at="2026-01-01T00:00:00+00:00",
        files=["src/parser.py"],
    )

    provider = ArtifactProvider(
        [past, future],
        as_of=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    result = provider.score(
        [make_entity()],
        "Fix invalid token parser",
    )

    assert len(result["parser"]) == 1
    assert result["parser"][0].detail["artifact"] == "PR#1"


def test_all_weights_are_between_zero_and_one():
    artifacts = [
        make_artifact(
            number=1,
            title="Fix invalid token parser",
            body="Parser invalid token",
            files=["src/parser.py"],
        ),
        make_artifact(
            number=2,
            title="Fix parser token",
            body="Parser token handling",
            files=["src/parser.py"],
        ),
    ]

    provider = ArtifactProvider(artifacts)
    result = provider.score(
        [make_entity()],
        "Fix invalid token parser",
    )

    assert result
    for evidence_list in result.values():
        for evidence in evidence_list:
            assert evidence.type == "artifact"
            assert 0.0 <= evidence.weight <= 1.0
            assert evidence.detail
            assert "artifact" in evidence.detail
            assert "link" in evidence.detail
            assert "confidence" in evidence.detail


def test_whole_word_mention_does_not_match_partial_identifier():
    artifact = make_artifact(
        title="Fix invalid token",
        body="The parser issue occurs here.",
    )
    entity = make_entity(
        entity_id="parse",
        name="parse",
        path="src/parse.py",
    )

    provider = ArtifactProvider([artifact])
    result = provider.score(
        [entity],
        "Fix invalid token in parse",
    )

    assert "parse" not in result


def test_loader_reads_iso_datetime(tmp_path):
    import json

    path = tmp_path / "artifacts.json"
    path.write_text(
        json.dumps(
            [
                {
                    "kind": "pr",
                    "number": 123,
                    "title": "Fix invalid token",
                    "body": "Fix the parser",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "files": ["src/parser.py"],
                }
            ]
        ),
        encoding="utf-8",
    )

    artifacts = load_artifacts(path)

    assert len(artifacts) == 1
    assert artifacts[0].number == 123
    assert artifacts[0].created_at == datetime(
        2025, 1, 1, tzinfo=timezone.utc
    )
    assert artifacts[0].files == ["src/parser.py"]
