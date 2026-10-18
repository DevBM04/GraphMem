"""HistoryProvider v1 (file-level git churn). Every test builds a real tiny git
repo with controlled commit dates, so recency and the as_of rule are checked
against actual `git log` output."""
import math
import os
import shutil
import subprocess

import pytest

from graphmem.graph.builder import GraphBuilder
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.parsing.python_parser import PythonParser
from graphmem.ranking.config import RankConfig
from graphmem.retrieval.localizer import Localizer
from graphmem.retrieval.providers.history import HistoryProvider, parse_git_log

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

T0 = 1_600_000_000  # fixed epoch far in the past: nothing here may depend on "today"
DAY = 86400


class Repo:
    """A throwaway git repo whose commit dates we control."""

    def __init__(self, path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self._git("init", "-q")
        self._n = 0

    def _git(self, *args, when=None):
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "tester", "GIT_COMMITTER_EMAIL": "tester@example.com",
        }
        if when is not None:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{when} +0000"
        done = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True, text=True, env=env, check=True,
        )
        return done.stdout

    def commit(self, files, message, when):
        """files: list of paths (content auto-generated) or {path: content}."""
        if not isinstance(files, dict):
            files = {}.fromkeys(files)
        for rel, text in files.items():
            self._n += 1
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text if text is not None else f"x = {self._n}\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("-c", "commit.gpgsign=false", "commit", "-q", "--no-verify",
                  "-m", message, when=when)
        return self._git("rev-parse", "HEAD").strip()


def scope(path, kind=EntityType.FILE, name=None):
    name = name or path
    return CodeEntity(id=f"{kind.value}:{path}:{name}", type=kind, name=name, path=path)


def only(out, entity):
    (ev,) = out[entity.id]
    return ev


# ---------------------------------------------------------------- contract
def test_evidence_shape_and_format(tmp_path):
    repo = Repo(tmp_path / "r")
    subjects = ["add parser", "tweak parser", "Fix tokenizer crash", "refactor parser"]
    shas = [repo.commit(["parser.py"], s, T0 + i * DAY) for i, s in enumerate(subjects)]

    provider = HistoryProvider(str(repo.path))
    assert provider.signal == "history"

    target = scope("parser.py")
    ev = only(provider.score([target], "unrelated words"), target)

    assert ev.type == "history"
    assert 0 < ev.weight <= 1
    assert ev.weight == pytest.approx(sum(math.exp(-d / 180) for d in (0, 1, 2, 3)) / 5)
    assert ev.detail["level"] == "file"
    assert ev.detail["commits"] == [  # newest first, at most 3
        f"{shas[3][:7]} refactor parser",
        f"{shas[2][:7]} Fix tokenizer crash",
        f"{shas[1][:7]} tweak parser",
    ]
    assert ev.source == f"4 commits touched parser.py (latest {shas[3][:7]}: 'refactor parser')"


def test_singular_wording_for_one_commit(tmp_path):
    repo = Repo(tmp_path / "r")
    sha = repo.commit(["solo.py"], "add solo", T0)
    target = scope("solo.py")
    ev = only(HistoryProvider(str(repo.path)).score([target], "x"), target)
    assert ev.source == f"1 commit touched solo.py (latest {sha[:7]}: 'add solo')"


# ------------------------------------------------------------ anti-leakage
def test_commits_after_as_of_are_excluded(tmp_path):
    repo = Repo(tmp_path / "r")
    a = repo.commit(["a.py"], "add a", T0)
    b = repo.commit(["a.py", "b.py"], "Fix tokenizer crash in b", T0 + DAY)
    c = repo.commit(["a.py", "c.py"], "later change", T0 + 2 * DAY)
    scopes = [scope("a.py"), scope("b.py"), scope("c.py")]

    past = HistoryProvider(str(repo.path), as_of=a)
    head = HistoryProvider(str(repo.path))

    # as_of=a sees only commit a ...
    assert [cm.sha for cm in past.commits] == [a]
    past_out = past.score(scopes, "tokenizer crash")
    assert set(past_out) == {scopes[0].id}          # b.py / c.py did not exist yet
    ev = only(past_out, scopes[0])
    assert ev.detail["commits"] == [f"{a[:7]} add a"]
    assert b[:7] not in ev.source and c[:7] not in ev.source

    # ... while HEAD sees everything, so the filtering above is real.
    assert [cm.sha for cm in head.commits] == [c, b, a]
    assert set(head.score(scopes, "x")) == {s.id for s in scopes}

    # a middle commit includes itself and its ancestors only.
    assert [cm.sha for cm in HistoryProvider(str(repo.path), as_of=b).commits] == [b, a]


def test_age_is_measured_from_as_of_commit_not_today(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["old.py"], "add old", T0)
    repo.commit(["new.py"], "add new", T0 + 180 * DAY)  # exactly 180 days newer

    old, new = scope("old.py"), scope("new.py")
    out = HistoryProvider(str(repo.path)).score([old, new], "banana")

    # Relative to the newest commit: age 0 -> w=1, age 180d -> w=e^-1.
    # (Measured from today, both weights would be ~0 since the repo is from 2020.)
    assert only(out, new).weight == pytest.approx(1 / 5)
    assert only(out, old).weight == pytest.approx(math.exp(-1) / 5)


# ----------------------------------------------------------------- scoring
def test_weight_is_capped_at_one(tmp_path):
    repo = Repo(tmp_path / "r")
    for i in range(7):  # 7 same-time commits: raw sum 7/5 = 1.4
        repo.commit(["hot.py"], f"change {i}", T0)
    target = scope("hot.py")
    ev = only(HistoryProvider(str(repo.path)).score([target], "x"), target)
    assert ev.weight == 1.0


def test_message_bonus_needs_two_shared_tokens(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["parser.py"], "Fix tokenizer crash", T0)
    provider = HistoryProvider(str(repo.path))
    target = scope("parser.py")

    one_shared = only(provider.score([target], "tokenizer fails sometimes"), target)
    two_shared = only(provider.score([target], "tokenizer crash on empty input"), target)

    assert one_shared.weight == pytest.approx(1 / 5)
    assert two_shared.weight == pytest.approx((1 + 0.2) / 5)  # bonus joins the sum, then /5


def test_bonus_still_respects_the_cap(tmp_path):
    repo = Repo(tmp_path / "r")
    for i in range(5):
        repo.commit(["parser.py"], "Fix tokenizer crash", T0)
    target = scope("parser.py")
    ev = only(HistoryProvider(str(repo.path)).score([target], "tokenizer crash"), target)
    assert ev.weight == 1.0


# -------------------------------------------------------------- scope rules
def test_every_scope_in_a_touched_file_gets_its_own_evidence(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["pkg/mod.py"], "add mod", T0)
    file_s = scope("pkg/mod.py")
    cls_s = scope("pkg/mod.py", EntityType.CLASS, "Mod")
    meth_s = scope("pkg/mod.py", EntityType.METHOD, "Mod.run")

    out = HistoryProvider(str(repo.path)).score([file_s, cls_s, meth_s], "x")

    evs = [only(out, s) for s in (file_s, cls_s, meth_s)]
    assert len({e.weight for e in evs}) == 1
    assert len({id(e) for e in evs}) == 3                         # no shared instances
    assert len({id(e.detail["commits"]) for e in evs}) == 3       # nor shared lists


def test_untouched_nonpython_and_pathless_scopes_get_nothing(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["a.py", "README.md"], "add files", T0)

    pathless = CodeEntity(id="e:none", type=EntityType.FUNCTION, name="f", path=None)
    scopes = [scope("a.py"), scope("README.md"), scope("missing.py"), pathless]
    out = HistoryProvider(str(repo.path)).score(scopes, "x")

    assert set(out) == {scopes[0].id}


def test_windows_style_entity_paths_match_git_paths(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["pkg/mod.py"], "add mod", T0)
    target = scope("pkg\\mod.py")
    out = HistoryProvider(str(repo.path)).score([target], "x")
    assert only(out, target).type == "history"


def test_parsed_folder_inside_larger_repo_uses_relative_paths(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["proj/a.py", "other/c.py"], "add files", T0)

    provider = HistoryProvider(str(repo.path / "proj"))
    assert provider.commits[0].files == ("a.py",)   # not 'proj/a.py', 'other/c.py'

    a, c = scope("a.py"), scope("c.py")
    out = provider.score([a, c], "x")
    assert set(out) == {a.id}


def test_max_commits_limits_the_window(tmp_path):
    repo = Repo(tmp_path / "r")
    for i in range(4):
        repo.commit(["a.py"], f"change {i}", T0 + i * DAY)
    provider = HistoryProvider(str(repo.path), max_commits=2)
    assert len(provider.commits) == 2
    target = scope("a.py")
    assert only(provider.score([target], "x"), target).source.startswith("2 commits touched")


def test_empty_scopes_and_history_free_repo(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["README.md"], "docs only", T0)   # no .py history at all
    provider = HistoryProvider(str(repo.path))
    assert provider.commits == []
    assert provider.score([scope("a.py")], "x") == {}
    assert provider.score([], "x") == {}


# ------------------------------------------------------------------ errors
def test_rejects_bad_arguments(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["a.py"], "add a", T0)
    for bad in ("", "--output=leak.txt", "-n1"):
        with pytest.raises(ValueError):
            HistoryProvider(str(repo.path), as_of=bad)
    with pytest.raises(ValueError):
        HistoryProvider(str(repo.path), max_commits=0)


def test_git_failures_raise_runtime_error(tmp_path):
    repo = Repo(tmp_path / "r")
    repo.commit(["a.py"], "add a", T0)
    with pytest.raises(RuntimeError):
        HistoryProvider(str(repo.path), as_of="no-such-revision")
    with pytest.raises(RuntimeError):
        HistoryProvider(str(tmp_path / "does-not-exist"))


# ------------------------------------------------------------------ parser
def test_parse_git_log_handles_pipes_crlf_and_bad_headers():
    raw = (
        "@@C|aaaa|100|fix | pipe\r\n\r\na.py\r\nb/c.py\r\n"
        "@@C|bbbb|50|no files\r\n"
        "@@C|bad-header\r\nlost.py\r\n"
        "@@C|cccc|notanint|x\r\nlost2.py\r\n"
        "@@C|dddd|10|last\r\n\r\nz.py\r\n"
    )
    got = [(c.sha, c.unix_time, c.subject, c.files) for c in parse_git_log(raw)]
    assert got == [
        ("aaaa", 100, "fix | pipe", ("a.py", "b/c.py")),
        ("bbbb", 50, "no files", ()),
        ("dddd", 10, "last", ("z.py",)),
    ]


# -------------------------------------------------------------- integration
def test_plugs_into_localizer_with_real_parser_paths(tmp_path):
    """entity.path from the real parser must line up with git's paths."""
    repo = Repo(tmp_path / "r")
    auth = (
        "def hash_password(raw):\n    return raw\n\n"
        "def login(user, raw):\n    return hash_password(raw) == user.password\n"
    )
    billing = "def charge(amount):\n    return amount * 2\n"
    repo.commit({"auth.py": auth, "billing.py": billing}, "add modules", T0)
    repo.commit({"auth.py": auth + "# tweak\n"}, "Fix login crash", T0 + DAY)

    graph = GraphBuilder().build(PythonParser().parse_repository(str(repo.path)))
    localizer = Localizer(
        graph,
        config=RankConfig().with_weights(history=0.3),
        providers=[HistoryProvider(str(repo.path))],
    )
    result = localizer.localize("login is broken")

    login = {h.entity.qualified_name: h for h in result.scopes}["login"]
    history = [e for e in login.evidence if e.type == "history"]
    assert history and history[0].detail["level"] == "file"
    assert "auth.py" in history[0].source
    assert login.signals["history"] > 0
