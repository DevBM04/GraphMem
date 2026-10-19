"""History evidence provider v1: file-level git churn (ADR-12/13/16).

Code that changed often and recently is more likely to hold a bug, and
commit subjects such as "fix tokenizer crash" are lexical clues. This
provider turns `git log` into ranking evidence:

    file score = min(1, sum(recency weight of each commit touching it) / 5)
    recency weight = exp(-age_days / 180)

Anti-leakage (ADR-13): history is read with `git log <as_of>`, so only
commits reachable from `as_of` are ever seen. Age is measured from the
newest commit in that window, never from today's date, so a benchmark
task from 2021 scores the same whenever it is run.
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath

from graphmem.indexing.code_index import tokenize
from graphmem.models.entities import CodeEntity
from graphmem.retrieval.evidence import Evidence

DECAY_DAYS = 180.0        # recency half-life-ish constant: w = exp(-age / 180)
SATURATION = 5.0          # summed recency weight at which a file scores 1.0
MESSAGE_BONUS = 0.2       # added to a commit's contribution on a subject match
MIN_SHARED_TOKENS = 2     # subject/issue tokens needed to earn the bonus
MAX_LISTED_COMMITS = 3    # commits quoted in Evidence.detail
SECONDS_PER_DAY = 86400.0

_COMMIT_PREFIX = "@@C|"


@dataclass(frozen=True)
class Commit:
    sha: str
    unix_time: int
    subject: str
    files: tuple[str, ...]


def parse_git_log(output: str) -> list[Commit]:
    """Parse `--name-only --format=@@C|%H|%ct|%s` output, in log order.

    A line starting with '@@C|' opens a commit; every following non-empty
    line is a file path. The subject is split off last so it may itself
    contain '|'. Malformed header lines are skipped along with their files.
    """
    commits: list[Commit] = []
    header: tuple[str, int, str] | None = None
    files: list[str] = []

    def flush() -> None:
        if header is not None:
            sha, unix_time, subject = header
            commits.append(Commit(sha, unix_time, subject, tuple(dict.fromkeys(files))))

    for raw in output.split("\n"):
        line = raw.rstrip("\r")
        if line.startswith(_COMMIT_PREFIX):
            flush()
            files = []
            parts = line.split("|", 3)
            try:
                header = (parts[1], int(parts[2]), parts[3]) if len(parts) == 4 else None
            except ValueError:
                header = None
        elif line and header is not None:
            files.append(line)
    flush()
    return commits


def _normalize(path: str | None) -> str | None:
    """Entity paths are repo-relative; compare them in git's '/' form."""
    if not path:
        return None
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path or None


class HistoryProvider:
    """EvidenceProvider (signal='history') backed by one `git log` call."""

    signal = "history"

    def __init__(self, repo_path: str, as_of: str = "HEAD", max_commits: int = 300) -> None:
        # as_of may come from benchmark data; never let it parse as a git option.
        if not as_of or as_of.startswith("-"):
            raise ValueError(f"invalid as_of revision: {as_of!r}")
        if max_commits < 1:
            raise ValueError("max_commits must be >= 1")

        self.repo_path = str(repo_path)
        self.as_of = as_of
        self.max_commits = max_commits

        self.commits: list[Commit] = parse_git_log(self._run_git_log())

        # Age is relative to the newest commit in the window (the as_of
        # commit), not to the wall clock.
        self.reference_time = max((c.unix_time for c in self.commits), default=0)
        self._weights = [
            math.exp(-max(0.0, (self.reference_time - c.unix_time) / SECONDS_PER_DAY) / DECAY_DAYS)
            for c in self.commits
        ]
        self._subject_tokens = [frozenset(tokenize(c.subject)) for c in self.commits]
        self._by_file: dict[str, list[int]] = {}
        for i, commit in enumerate(self.commits):
            for path in commit.files:
                self._by_file.setdefault(path, []).append(i)

    # ------------------------------------------------------------------
    def _run_git_log(self) -> str:
        # `--relative` makes paths relative to repo_path rather than the git
        # top-level, so they match CodeEntity.path even when the parsed folder
        # is a subdirectory of a larger repository. `core.quotepath=off` keeps
        # non-ASCII file names unquoted.
        cmd = [
            "git", "-C", self.repo_path, "-c", "core.quotepath=off",
            "log", self.as_of, "--no-merges", "-n", str(self.max_commits),
            "--relative", "--name-only", f"--format={_COMMIT_PREFIX}%H|%ct|%s",
            "--", "*.py",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, encoding="utf-8", errors="replace", check=False
            )
        except OSError as exc:  # git not installed / repo_path not a directory
            raise RuntimeError(f"could not run git: {exc}") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"git log failed for {self.repo_path!r} at {self.as_of!r}: {proc.stderr.strip()}"
            )
        return proc.stdout

    # ------------------------------------------------------------------
    def score(self, scopes: list[CodeEntity], issue: str) -> dict[str, list[Evidence]]:
        """Evidence for every scope whose file was touched in the window."""
        if not scopes or not self._by_file:
            return {}

        issue_tokens = set(tokenize(issue))
        per_file: dict[str, tuple[float, str, list[str]] | None] = {}
        out: dict[str, list[Evidence]] = {}

        for scope in scopes:
            path = _normalize(scope.path)
            if path is None:
                continue
            if path not in per_file:
                per_file[path] = self._file_evidence(path, issue_tokens)
            found = per_file[path]
            if found is None:
                continue
            weight, source, listed = found
            out[scope.id] = [
                Evidence("history", source, weight, {"commits": list(listed), "level": "file"})
            ]
        return out

    def _file_evidence(
        self, path: str, issue_tokens: set[str]
    ) -> tuple[float, str, list[str]] | None:
        indices = self._by_file.get(path)
        if not indices:
            return None

        # The message bonus joins each commit's contribution *before* summing
        # and capping, so a matching commit adds 0.2 / SATURATION to the score.
        total = 0.0
        for i in indices:
            contribution = self._weights[i]
            if len(self._subject_tokens[i] & issue_tokens) >= MIN_SHARED_TOKENS:
                contribution += MESSAGE_BONUS
            total += contribution
        weight = min(1.0, total / SATURATION)
        if weight <= 0.0:
            return None

        # Newest first; log order breaks timestamp ties.
        newest = sorted(indices, key=lambda i: (-self.commits[i].unix_time, i))
        listed = [
            f"{self.commits[i].sha[:7]} {self.commits[i].subject}"
            for i in newest[:MAX_LISTED_COMMITS]
        ]
        latest = self.commits[newest[0]]
        noun = "commit" if len(indices) == 1 else "commits"
        source = (
            f"{len(indices)} {noun} touched {PurePosixPath(path).name} "
            f"(latest {latest.sha[:7]}: '{latest.subject}')"
        )
        return weight, source, listed
