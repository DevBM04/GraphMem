"""Persistent cache for parsed repositories.

Cache entries are local pickle files keyed by repository path, Git commit, and
parser configuration. Cache files are written atomically so interrupted parses
cannot leave a partially-written entry.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, TypeVar

from graphmem.models.repository import ParsedRepository

TParser = TypeVar("TParser")
CACHE_VERSION = 1


def _commit_sha(repo: Path) -> str:
    """Return the full HEAD SHA, or a stable fallback outside Git repositories."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "no-git"


def _working_tree_fingerprint(repo: Path) -> str:
    """Detect uncommitted source changes without hashing every source byte."""
    digest = hashlib.sha256()
    try:
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
        digest.update(status.encode())
        # Include metadata for changed/untracked files; status alone does not
        # distinguish two successive edits to the same tracked file.
        for line in status.splitlines():
            rel = line[3:].split(" -> ")[-1]
            path = repo / rel
            try:
                stat = path.stat()
                digest.update(f"{rel}\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode())
            except OSError:
                digest.update(f"{rel}\0missing\0".encode())
    except (OSError, subprocess.SubprocessError):
        # Non-Git repositories are keyed by a lightweight source-file metadata
        # scan so edits still invalidate the cache.
        for path in sorted(repo.rglob("*.py")):
            if any(part in {".git", ".cache", "venv", ".venv"} for part in path.parts):
                continue
            try:
                stat = path.stat()
                digest.update(f"{path.relative_to(repo)}\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode())
            except OSError:
                continue
    return digest.hexdigest()


def _parser_signature(parser: object) -> str:
    config = {
        "class": f"{type(parser).__module__}.{type(parser).__qualname__}",
        "excluded_dirs": sorted(getattr(parser, "excluded_dirs", []) or []),
        "language": getattr(parser, "language", None),
    }
    return hashlib.sha256(repr(config).encode()).hexdigest()


def _default_cache_dir() -> Path:
    # src/graphmem/ingestion/cache.py -> repository root
    return Path(__file__).resolve().parents[3] / ".cache" / "graphmem"


def load_or_parse(
    repo_path: str | Path,
    parser: object,
    *,
    cache_dir: str | Path | None = None,
) -> ParsedRepository:
    """Load a cached ``ParsedRepository`` or parse and persist it.

    The key includes the resolved repository path and full HEAD commit SHA.
    Parser configuration and dirty-tree metadata are stored in the cache
    envelope to prevent reuse across incompatible parser settings or edits.
    ``parser`` must provide ``parse_repository(str_path)``.
    """
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise NotADirectoryError(str(repo))

    commit = _commit_sha(repo)
    dirty_fingerprint = _working_tree_fingerprint(repo)
    parser_signature = _parser_signature(parser)
    key_payload = f"{repo}\0{commit}\0{parser_signature}".encode()
    key = hashlib.sha256(key_payload).hexdigest()
    root = Path(cache_dir).expanduser().resolve() if cache_dir else _default_cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    cache_file = root / f"{key}.pickle"

    try:
        with cache_file.open("rb") as stream:
            envelope = pickle.load(stream)
        if (
            envelope.get("cache_version") == CACHE_VERSION
            and envelope.get("repository_path") == str(repo)
            and envelope.get("commit") == commit
            and envelope.get("dirty_fingerprint") == dirty_fingerprint
            and envelope.get("parser_signature") == parser_signature
            and isinstance(envelope.get("parsed"), ParsedRepository)
        ):
            return envelope["parsed"]
    except (OSError, EOFError, pickle.PickleError, AttributeError, ValueError, TypeError):
        pass

    parsed = parser.parse_repository(str(repo))
    if not isinstance(parsed, ParsedRepository):
        raise TypeError("parser.parse_repository() must return ParsedRepository")

    envelope = {
        "cache_version": CACHE_VERSION,
        "repository_path": str(repo),
        "commit": commit,
        "dirty_fingerprint": dirty_fingerprint,
        "parser_signature": parser_signature,
        "parsed": parsed,
    }
    fd, temp_name = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            pickle.dump(envelope, stream, protocol=pickle.HIGHEST_PROTOCOL)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, cache_file)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return parsed
