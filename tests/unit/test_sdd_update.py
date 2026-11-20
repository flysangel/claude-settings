"""Unit tests for home/skills/sdd-update/scripts/sdd_update.py.

The official tool is replaced by a fake that writes one of two small versions of
Spec Kit (conftest: OLD_VERSION and NEW_VERSION), and the version lookup by a
function that returns a fixed version, so nothing here needs the network.
Contracts: specs/004-sdd-update/contracts/cli.md and specs/004-sdd-update/data-model.md.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    NEW_VERSION,
    OLD_VERSION,
    SDD_INIT_PY,
    SDD_UPDATE_PY,
    git_run,
    init_with_version,
    snapshot,
    versioned_official_files,
    write_tree,
    write_versioned_official_output,
)

RECORD = ".specify/sdd-init.json"
GITATTRIBUTES = ".specify/.gitattributes"
GITATTRIBUTES_BYTES = b"scripts/bash/*.sh text eol=lf\n"
COPIES = ".specify/sdd-update/"

OLD = versioned_official_files(OLD_VERSION)
NEW = versioned_official_files(NEW_VERSION)
PROTECTED = ".specify/memory/"

# What a fresh update from OLD to NEW does to an untouched project.
UPDATED = sorted(p for p in NEW if p in OLD and NEW[p] != OLD[p] and not p.startswith(PROTECTED))
CREATED = sorted(p for p in NEW if p not in OLD)
REMOVED = sorted(p for p in OLD if p not in NEW)
SAME = sorted(p for p in NEW if p in OLD and NEW[p] == OLD[p])

NOT_UPDATED_NO_RECORD = (
    "Spec Kit was not updated: this project has no sdd-init record. "
    "Run /sdd-init first, then run /sdd-update again."
)
NOT_UPDATED_BAD_RECORD = "Spec Kit was not updated: .specify/sdd-init.json cannot be used. Nothing was changed."
NOT_UPDATED_INTERRUPTED = (
    "Spec Kit was not updated: the setup by /sdd-init was interrupted. "
    "Run /sdd-init to finish it, then run /sdd-update again."
)
NOT_UPDATED_NO_SDD_INIT = (
    "Spec Kit was not updated: the sdd-init skill is not installed next to sdd-update. Nothing was changed."
)
MISSING_TOOLS = "Missing required tools. Nothing was changed. Install them and run /sdd-update again."
GIT_NOTHING = (
    "Git: nothing was added to the index and nothing was committed. "
    "Review the update with git status, then commit it."
)
GIT_NOT_A_REPO = (
    "Git: not a git repository, and none was created. Executable bits cannot be recorded "
    "until the files are added with: git add --chmod=+x .specify/scripts/bash/*.sh"
)
NEXT = (
    "Next: compare each kept file with its .new copy under .specify/sdd-update/, "
    "merge what you want, then delete the copies."
)
WRITE_FAILED_HINT = (
    "Some files may already have been updated. Fix the cause, then run /sdd-update again; "
    "it finishes the update and never overwrites a file you changed."
)


def line(action: str, rest: str) -> str:
    return f"{action:<10}{rest}"


def git_added(n: int) -> str:
    return (
        f"Git: {n} files were added to the index and nothing was committed. "
        "Review the update with git status, then commit it."
    )


def summary(old: str, new: str, u: int, c: int, r: int, k: int) -> str:
    return f"Spec Kit updated from {old} to {new}: {u} updated, {c} created, {r} removed, {k} kept."


def already(version: str = NEW_VERSION) -> str:
    return f"Spec Kit {version} is already the latest stable release. Nothing changed."


def unavailable(reason: str) -> str:
    return (
        f"Could not get the latest stable Spec Kit release: {reason}. Nothing was changed. "
        "Check the network connection and run /sdd-update again."
    )


def copy_of(path: str) -> str:
    return f"{COPIES}{path}.new"


def kept_modified(path: str) -> str:
    return line("kept", f"{path} (modified; new version: {copy_of(path)})")


def kept_foreign(path: str) -> str:
    return line("kept", f"{path} (not created by sdd-init; new version: {copy_of(path)})")


def kept_orphan(path: str, version: str = NEW_VERSION) -> str:
    return line("kept", f"{path} (modified; no longer part of Spec Kit {version})")


def kept_pending(path: str, version: str = NEW_VERSION) -> str:
    return line("kept", f"{path} (still differs from Spec Kit {version}; new version: {copy_of(path)})")


def staged_line(path: str) -> str:
    return line("staged", f"{path} (executable bit recorded in the git index)")


def snap(root: Path, with_mtime: bool = False) -> dict:
    """Snapshot of the project without git's own directory."""
    return {
        k: v
        for k, v in snapshot(root, with_mtime=with_mtime).items()
        if k != ".git/" and not k.startswith(".git/")
    }


def read_record(root: Path) -> dict:
    return json.loads((root / RECORD).read_bytes().decode("utf-8"))


def entries(root: Path) -> dict[str, dict]:
    return {e["path"]: e for e in read_record(root)["entries"]}


def index(root: Path) -> dict[str, str]:
    out = git_run(root, "ls-files", "-s")
    result = {}
    for row in out.splitlines():
        meta, path = row.split("\t", 1)
        result[path] = meta.split(" ")[0]
    return result


def status(root: Path) -> str:
    return git_run(root, "status", "--porcelain", "--untracked-files=all")


def commit_all(root: Path, message: str = "commit") -> None:
    git_run(root, "add", "-A")
    git_run(root, "commit", "--quiet", "-m", message)


def head(root: Path) -> str:
    return git_run(root, "rev-parse", "HEAD").strip()


def of(lines: list[str], action: str) -> list[str]:
    return [l for l in lines if l.split(" ", 1)[0] == action]


def sha(sdd_init, content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return sdd_init.content_hash(content)


class UpdateRunner:
    """Runs sdd_update.main() in-process with replaceable steps and records how they were used."""

    def __init__(self, module, shared, capsys, monkeypatch):
        self.module = module
        self.shared = shared
        self.capsys = capsys
        self.monkeypatch = monkeypatch
        self.latest = NEW_VERSION
        self.version_calls = 0
        self.official_versions: list[str] = []
        self.dests: list[Path] = []
        self.resolve_error: str | None = None
        self.official_error: str | None = None
        self.produced_version: str | None = None
        self.extra_output: dict[str, str] = {}

    def resolve(self) -> str:
        self.version_calls += 1
        if self.resolve_error:
            raise self.shared.StepFailed(self.resolve_error)
        return self.latest

    def official(self, version: str, dest: Path) -> None:
        self.official_versions.append(version)
        self.dests.append(Path(dest))
        assert list(Path(dest).iterdir()) == [], "the official tool must run in an empty directory"
        if self.official_error:
            raise self.shared.StepFailed(self.official_error)
        write_versioned_official_output(Path(dest), self.produced_version or version)
        write_tree(Path(dest), self.extra_output)

    def reset(self) -> None:
        self.version_calls = 0
        self.official_versions.clear()
        self.dests.clear()

    def run(self, root: Path, *args: str) -> tuple[int, list[str], str]:
        self.monkeypatch.chdir(root)
        self.capsys.readouterr()
        code = self.module.main(list(args), resolve_version=self.resolve, run_official=self.official)
        captured = self.capsys.readouterr()
        return code, captured.out.splitlines(), captured.err


@pytest.fixture
def runner(sdd_update, sdd_init, capsys, monkeypatch):
    shared = sdd_update.load_sdd_init()
    assert shared is sdd_init, "sdd_update must use the very sdd_init module the tests patch"
    return UpdateRunner(sdd_update, shared, capsys, monkeypatch)


@pytest.fixture
def old_project(sdd_init, make_project, capsys):
    """Factory: a project with OLD_VERSION brought in by sdd-init (fake official tool)."""

    def factory(git: bool = True, commit: bool = True) -> Path:
        root = make_project(git=git)
        assert init_with_version(sdd_init, root, OLD_VERSION) == 0
        capsys.readouterr()
        if git and commit:
            commit_all(root, "spec kit old")
        return root

    return factory


# ===================================================================== core


def load_probe(path: Path, name: str, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_loading_as_a_module_does_nothing_and_loads_nothing_else(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(sys.modules, "sdd_init", raising=False)
    before = set(sys.modules)

    module = load_probe(SDD_UPDATE_PY, "sdd_update_probe", monkeypatch)

    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert list(tmp_path.iterdir()) == []
    assert "sdd_init" not in sys.modules
    repo = str(SDD_UPDATE_PY.parents[3])
    for name in set(sys.modules) - before - {"sdd_update_probe"}:
        assert not str(getattr(sys.modules[name], "__file__", "") or "").startswith(repo), name
    assert callable(module.main)


def test_shared_code_is_the_adjacent_sdd_init(sdd_update, sdd_init):
    path = sdd_update.sdd_init_path()

    assert os.path.samefile(path, SDD_INIT_PY)
    assert Path(path).parts[-3:] == ("sdd-init", "scripts", "sdd_init.py")
    assert sdd_update.load_sdd_init() is sdd_init


def test_without_an_adjacent_sdd_init_exit_1_and_change_nothing(tmp_path, make_project, monkeypatch, capsys):
    lonely = tmp_path / "skills" / "sdd-update" / "scripts" / "sdd_update.py"
    lonely.parent.mkdir(parents=True)
    shutil.copy(SDD_UPDATE_PY, lonely)
    module = load_probe(lonely, "sdd_update_lonely", monkeypatch)
    root = make_project(git=True)
    write_tree(root, {"keep.txt": "x\n"})
    before = snap(root, with_mtime=True)
    monkeypatch.chdir(root)
    calls = []

    code = module.main([], resolve_version=lambda: calls.append("v") or NEW_VERSION, run_official=lambda v, d: calls.append(v))

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out.splitlines() == [NOT_UPDATED_NO_SDD_INIT]
    assert calls == []
    assert snap(root, with_mtime=True) == before


@pytest.mark.parametrize("argv", [["1.4.3"], ["--version", "1.0"], ["--help"], ["update"], ["--downgrade"]])
def test_any_argument_exits_1_with_usage(runner, old_project, argv):
    root = old_project()
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root, *argv)

    assert code == 1
    assert err.splitlines()[0] == "usage: sdd_update.py"
    assert out == []
    assert runner.version_calls == 0 and runner.official_versions == []
    assert snap(root, with_mtime=True) == before


def test_exit_codes_are_those_of_sdd_init(sdd_update, sdd_init):
    assert (sdd_update.EXIT_OK, sdd_update.EXIT_FAILED, sdd_update.EXIT_MISSING_TOOLS, sdd_update.EXIT_UNAVAILABLE) == (
        sdd_init.EXIT_OK,
        sdd_init.EXIT_FAILED,
        sdd_init.EXIT_MISSING_TOOLS,
        sdd_init.EXIT_UNAVAILABLE,
    ) == (0, 1, 3, 4)
    codes = {name for name in dir(sdd_update) if name.startswith("EXIT_")}
    assert codes == {"EXIT_OK", "EXIT_FAILED", "EXIT_MISSING_TOOLS", "EXIT_UNAVAILABLE"}


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("1.4.3", "1.4.3", 0),
        ("1.4", "1.4.0", 0),
        ("1.4.10", "1.4.9", 1),
        ("1.10.0", "1.9.9", 1),
        ("2", "1.99.99", 1),
        ("1.2.6", "1.4.3", -1),
        ("1.5.0rc1", "1.4.3", 1),
        ("1.4.3rc1", "1.4.3", 0),
        ("1.4.3.1", "1.4.3", 1),
    ],
)
def test_version_numbers_compare_by_their_leading_numeric_parts(sdd_update, a, b, expected):
    assert sdd_update.compare_versions(a, b) == expected
    assert sdd_update.compare_versions(b, a) == -expected


def test_version_numbers_take_the_leading_numeric_parts(sdd_update):
    assert sdd_update.version_numbers("1.5.0rc1") == (1, 5, 0)
    assert sdd_update.version_numbers("1.4.3") == (1, 4, 3)
    assert sdd_update.version_numbers("abc") == ()


@pytest.mark.parametrize(
    "recorded, options, latest, status, expected",
    [
        ("1.4.3", None, "1.4.3", "complete", "latest"),
        ("1.4.3", None, "1.4.3", "applying", "interrupted"),
        ("1.2.6", None, "1.4.3", "complete", "update"),
        ("1.2.6", None, "1.4.3", "applying", "update"),
        ("1.5.0", None, "1.4.3", "complete", "newer"),
        ("1.4.3", "1.5.0rc1", "1.4.3", "complete", "newer"),
        ("1.4.3", "1.5.0rc1", "1.4.3", "applying", "newer"),
        ("1.2.6", "1.4.3rc1", "1.4.3", "complete", "update"),
        ("1.2.6", "1.2.6", "1.4.3", "complete", "update"),
    ],
)
def test_decide_follows_the_four_cases_in_order(sdd_update, recorded, options, latest, status, expected):
    assert sdd_update.decide(recorded, options, latest, status) == expected


@pytest.mark.parametrize(
    "path",
    [
        ".specify/templates/plan-template.md",
        ".claude/skills/speckit-plan/SKILL.md",
        ".specify/.gitignore",
    ],
)
def test_copy_paths_map_both_ways(sdd_update, path):
    copy = sdd_update.copy_path(path)

    assert copy == f".specify/sdd-update/{path}.new"
    assert sdd_update.copy_target(copy) == path


@pytest.mark.parametrize("copy", [".specify/templates/a.md", ".specify/sdd-update/a.md", ".specify/sdd-update/.new"])
def test_paths_that_are_not_copies_have_no_target(sdd_update, copy):
    assert sdd_update.copy_target(copy) is None


def test_only_paths_under_memory_are_protected(sdd_update):
    assert sdd_update.is_protected(".specify/memory/constitution.md")
    assert sdd_update.is_protected(".specify/memory/.constitution-template.json")
    assert not sdd_update.is_protected(".specify/memoryx/a.md")
    assert not sdd_update.is_protected(".specify/templates/plan-template.md")
    assert not sdd_update.is_protected(".claude/skills/speckit-memory/SKILL.md")


def test_action_lines_pad_the_action_to_ten_characters(sdd_update):
    assert sdd_update.action_line("updated", "a/b") == "updated   a/b"
    assert sdd_update.action_line("kept", "x (y)") == "kept      x (y)"


@pytest.mark.parametrize("extra", [RECORD, ".specify/sdd-update/.specify/templates/plan-template.md.new", "notes.txt"])
def test_official_output_with_forbidden_paths_is_an_official_tool_failure(runner, old_project, extra):
    root = old_project()
    before = snap(root, with_mtime=True)
    runner.extra_output = {extra: "x\n"}

    code, out, err = runner.run(root)

    assert code == 4
    assert len(out) == 1 and out[0].startswith("Could not get the latest stable Spec Kit release: ")
    assert out[0].endswith(". Nothing was changed. Check the network connection and run /sdd-update again.")
    assert extra in out[0]
    assert snap(root, with_mtime=True) == before
    assert not runner.dests[0].exists()
