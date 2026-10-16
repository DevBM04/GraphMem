
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from graphmem.ingestion.cache import load_or_parse
from graphmem.models.repository import ParsedRepository


class FakeParser:
    language = "python"

    def __init__(self, excluded_dirs: set[str] | None = None) -> None:
        self.excluded_dirs = excluded_dirs or set()
        self.calls = 0

    def parse_repository(self, repository_path: str) -> ParsedRepository:
        self.calls += 1
        return ParsedRepository(repository_path=str(Path(repository_path).resolve()))


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    git(repo, "init")
    git(repo, "config", "user.email", "graphmem-test@example.com")
    git(repo, "config", "user.name", "GraphMem Test")

    (repo / "app.py").write_text("VALUE = 1\n")
    git(repo, "add", "app.py")
    git(repo, "commit", "-m", "initial")

    return repo


def test_cache_hit_reuses_parsed_repository(
    git_repo: Path, tmp_path: Path
) -> None:
    parser = FakeParser()
    cache_dir = tmp_path / "cache"

    first = load_or_parse(git_repo, parser, cache_dir=cache_dir)
    second = load_or_parse(git_repo, parser, cache_dir=cache_dir)

    assert first is not None
    assert second is not None
    assert parser.calls == 1
    assert first.repository_path == second.repository_path


def test_source_edit_invalidates_cache(
    git_repo: Path, tmp_path: Path
) -> None:
    parser = FakeParser()
    cache_dir = tmp_path / "cache"

    load_or_parse(git_repo, parser, cache_dir=cache_dir)
    (git_repo / "app.py").write_text("VALUE = 222\n")

    load_or_parse(git_repo, parser, cache_dir=cache_dir)

    assert parser.calls == 2


def test_parser_configuration_invalidates_cache(
    git_repo: Path, tmp_path: Path
) -> None:
    cache_dir = tmp_path / "cache"
    first_parser = FakeParser({"tests"})
    second_parser = FakeParser({"docs"})

    load_or_parse(git_repo, first_parser, cache_dir=cache_dir)
    load_or_parse(git_repo, second_parser, cache_dir=cache_dir)

    assert first_parser.calls == 1
    assert second_parser.calls == 1


def test_new_commit_does_not_reuse_old_entry(
    git_repo: Path, tmp_path: Path
) -> None:
    parser = FakeParser()
    cache_dir = tmp_path / "cache"

    load_or_parse(git_repo, parser, cache_dir=cache_dir)

    (git_repo / "app.py").write_text("VALUE = 2\n")
    git(git_repo, "add", "app.py")
    git(git_repo, "commit", "-m", "change value")

    load_or_parse(git_repo, parser, cache_dir=cache_dir)

    assert parser.calls == 2


def test_corrupt_cache_is_rebuilt(
    git_repo: Path, tmp_path: Path
) -> None:
    parser = FakeParser()
    cache_dir = tmp_path / "cache"

    load_or_parse(git_repo, parser, cache_dir=cache_dir)
    cache_files = list(cache_dir.glob("*.pickle"))
    assert len(cache_files) == 1

    cache_files[0].write_bytes(b"not a valid pickle")

    load_or_parse(git_repo, parser, cache_dir=cache_dir)

    assert parser.calls == 2
