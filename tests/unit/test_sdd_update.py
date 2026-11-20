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


# ============================================== US1: a fresh update (T012)


def test_fresh_update_replaces_creates_and_removes_untouched_files(runner, old_project):
    root = old_project()
    write_tree(root, {"specs/001-x/spec.md": "# my spec\n", "README.md": "mine\n"})
    commit_all(root, "content")
    before = snap(root, with_mtime=True)
    created_dirs_before = read_record(root)["created_dirs"]
    assert ".claude/skills/speckit-legacy" in created_dirs_before

    code, out, err = runner.run(root)

    assert code == 0, err
    assert err == ""
    sh_created = [p for p in CREATED if p.endswith(".sh")]
    assert out == (
        [line("updated", p) for p in UPDATED]
        + [line("created", p) for p in CREATED]
        + [line("removed", p) for p in REMOVED]
        + [staged_line(p) for p in sh_created]
        + [summary(OLD_VERSION, NEW_VERSION, len(UPDATED), len(CREATED), len(REMOVED), 0), git_added(len(sh_created))]
    )
    assert of(out, "kept") == [] and not any(l.startswith("Next:") for l in out)
    after = snap(root, with_mtime=True)
    for path in UPDATED + CREATED:
        assert (root / path).read_bytes() == NEW[path].encode("utf-8"), path
    for path in REMOVED:
        assert not os.path.lexists(root / path)
    assert not (root / ".claude/skills/speckit-legacy").exists()
    assert ".claude/skills/speckit-legacy" not in read_record(root)["created_dirs"]
    # Untouched: files that are the same in both versions, .specify/memory/, specs/ and everything not recorded.
    for key in SAME + [k for k in before if k.startswith(PROTECTED) or k.startswith("specs/")] + [
        "README.md",
        GITATTRIBUTES,
    ]:
        assert after[key] == before[key], key
    assert (root / ".specify/memory/constitution.md").read_bytes() == OLD[".specify/memory/constitution.md"].encode()
    # The staging directory is gone, and nothing of it was left in the project.
    assert runner.dests and not runner.dests[0].exists() and not runner.dests[0].parent.exists()
    assert not (root / ".specify/sdd-update").exists()
    assert not [k for k in after if k.endswith(".sdd-update-tmp")]
    assert runner.official_versions == [NEW_VERSION]


def test_fresh_update_output_paths_use_forward_slashes_and_are_sorted(runner, old_project):
    root = old_project()

    code, out, _ = runner.run(root)

    assert code == 0
    assert "\\" not in "\n".join(out)
    for action in ("updated", "created", "removed", "staged"):
        paths = [l.split()[1] for l in of(out, action)]
        assert paths == sorted(paths), action


# ================================================ US1: the record (T013)


def test_record_after_an_update(runner, sdd_init, old_project):
    root = old_project()
    before = entries(root)

    code, _, _ = runner.run(root)

    assert code == 0
    data = read_record(root)
    assert data["speckit_version"] == NEW_VERSION and data["status"] == "complete"
    after = entries(root)
    for path in UPDATED + CREATED + SAME:
        assert after[path]["sha256"] == sha(sdd_init, NEW[path]), path
        assert after[path]["origin"] == "speckit"
    for path in REMOVED:
        assert path not in after
    for path in [p for p in before if p.startswith(PROTECTED)] + [GITATTRIBUTES]:
        assert after[path] == before[path], path
    assert after[GITATTRIBUTES]["origin"] == "sdd-init"
    assert after[".specify/scripts/bash/setup-tasks.sh"]["staged_executable"] is True
    assert after[".specify/scripts/bash/markdown_sections.py"]["staged_executable"] is False
    # Entries already staged by sdd-init keep their flag.
    assert after[".specify/scripts/bash/common.sh"]["staged_executable"] is True
    paths = [e["path"] for e in data["entries"]]
    assert paths == sorted(paths)
    raw = (root / RECORD).read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert str(root).encode() not in raw and b"\\" not in raw
    assert data["created_dirs"] == sorted(data["created_dirs"])


def test_new_directories_are_added_to_created_dirs(runner, old_project, sdd_update, monkeypatch):
    root = old_project()
    extra = ".claude/skills/speckit-newone/SKILL.md"
    runner.extra_output = {extra: "---\nname: speckit-newone\n---\n"}

    code, out, _ = runner.run(root)

    assert code == 0
    assert line("created", extra) in out
    assert ".claude/skills/speckit-newone" in read_record(root)["created_dirs"]


def test_remove_by_sdd_init_after_an_update_deletes_what_nobody_changed(runner, sdd_init, old_project, capsys, monkeypatch):
    root = old_project(git=False)
    write_tree(root, {"specs/001-x/spec.md": "# mine\n"})
    runner.run(root)
    (root / ".specify/templates/plan-template.md").write_bytes(b"changed after update\n")

    monkeypatch.chdir(root)
    capsys.readouterr()
    code = sdd_init.main(["remove"])
    out = capsys.readouterr().out.splitlines()

    assert code == 0
    assert out[-1] == "Spec Kit removed: %d deleted, 1 kept because they were modified." % (len(of(out, "deleted")))
    assert of(out, "kept") == [line("kept", ".specify/templates/plan-template.md (modified since init)")]
    left = sorted(k for k in snap(root) if not k.endswith("/"))
    assert left == [".specify/templates/plan-template.md", "specs/001-x/spec.md"]


# ===================================== US1: nothing to update (T014)


@pytest.mark.parametrize("git", [True, False])
def test_already_latest_changes_nothing_and_does_not_run_the_official_tool(runner, old_project, git):
    root = old_project(git=git)
    runner.run(root)
    if git:
        commit_all(root, "updated")
    for attempt in range(5):
        before = snap(root, with_mtime=True)
        before_status = status(root) if git else None
        before_index = git_run(root, "ls-files", "-s") if git else None
        runner.reset()

        code, out, err = runner.run(root)

        assert code == 0
        assert out == [already()], attempt
        assert err == ""
        assert runner.version_calls == 1 and runner.official_versions == []
        assert snap(root, with_mtime=True) == before
        if git:
            assert status(root) == before_status
            assert git_run(root, "ls-files", "-s") == before_index


def set_record_version(root: Path, version: str, status_value: str | None = None) -> None:
    data = read_record(root)
    data["speckit_version"] = version
    if status_value:
        data["status"] = status_value
    (root / RECORD).write_bytes((json.dumps(data, indent=2) + "\n").encode())


def set_options_version(root: Path, value) -> None:
    path = root / ".specify/init-options.json"
    data = json.loads(path.read_bytes())
    data["speckit_version"] = value
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode())


@pytest.mark.parametrize(
    "recorded, options, shown",
    [
        ("1.2.0", None, "1.2.0"),
        (OLD_VERSION, "1.5.0rc1", "1.5.0rc1"),
        ("1.2.0", "1.5.0rc1", "1.5.0rc1"),
        ("1.6.0", "1.5.0rc1", "1.6.0"),
        ("1.5.0", "1.5.0rc1", "1.5.0"),
    ],
)
def test_newer_than_the_latest_stable_release_is_not_downgraded(runner, old_project, recorded, options, shown):
    root = old_project()
    set_record_version(root, recorded)
    if options is not None:
        set_options_version(root, options)
    commit_all(root, "edited")
    before = snap(root, with_mtime=True)
    runner.latest = NEW_VERSION

    code, out, err = runner.run(root)

    assert code == 0
    assert out == [f"Spec Kit {shown} is newer than the latest stable release {NEW_VERSION}. Nothing changed."]
    assert runner.official_versions == []
    assert snap(root, with_mtime=True) == before
    assert status(root) == ""


@pytest.mark.parametrize("problem", ["missing", "unparseable", "number", "list"])
def test_unusable_init_options_only_the_record_counts(runner, old_project, problem):
    root = old_project()
    path = root / ".specify/init-options.json"
    if problem == "missing":
        path.unlink()
    elif problem == "unparseable":
        path.write_bytes(b"{ not json")
    elif problem == "number":
        set_options_version(root, 99)
    else:
        path.write_bytes(b'["9.9.9"]')
    set_record_version(root, NEW_VERSION)
    before = snap(root, with_mtime=True)

    code, out, _ = runner.run(root)

    assert code == 0
    assert out == [already()]
    assert snap(root, with_mtime=True) == before


# ============================================== US1: stopping (T015)


@pytest.mark.parametrize("missing", [["uv"], ["git"], ["bash"], ["bash", "uv"], ["bash", "git", "uv"]])
def test_missing_tools_stop_before_anything(runner, old_project, monkeypatch, missing):
    root = old_project()
    before = snap(root, with_mtime=True)
    monkeypatch.setattr(runner.shared, "is_windows", lambda: False)
    monkeypatch.setattr(runner.shared, "find_tool", lambda name: None if name in missing else f"/bin/{name}")

    code, out, err = runner.run(root)

    assert code == 3
    assert out == [line("missing", name) for name in sorted(missing)] + [MISSING_TOOLS]
    for name in missing:
        assert name in err
    assert "/sdd-update" in err
    assert runner.version_calls == 0 and runner.official_versions == []
    assert snap(root, with_mtime=True) == before


def test_windows_missing_git_bash_uses_the_sdd_init_wording(runner, old_project, monkeypatch):
    root = old_project()
    monkeypatch.setattr(runner.shared, "is_windows", lambda: True)
    monkeypatch.setattr(runner.shared, "find_tool", lambda name: None if name == "bash" else f"/bin/{name}")

    code, out, err = runner.run(root)

    assert code == 3
    assert out == [line("missing", "bash (Git Bash, included with Git for Windows)"), MISSING_TOOLS]
    assert "Git Bash" in err


@pytest.mark.parametrize("layout", ["empty", "no .specify record", "spec kit without record"])
def test_without_a_record_exit_1_and_do_not_go_online(runner, make_project, layout):
    root = make_project(git=True)
    if layout == "no .specify record":
        write_tree(root, {".specify/templates/plan-template.md": "x\n"})
    elif layout == "spec kit without record":
        write_versioned_official_output(root, OLD_VERSION)
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root)

    assert code == 1
    assert out == [NOT_UPDATED_NO_RECORD]
    assert "/sdd-init" in err
    assert runner.version_calls == 0 and runner.official_versions == []
    assert snap(root, with_mtime=True) == before


def _record_with(change) -> dict:
    data = {
        "schema": 1,
        "status": "complete",
        "speckit_version": OLD_VERSION,
        "init_options": {"integration": "claude", "script": "sh"},
        "entries": [
            {"path": ".specify/templates/a.md", "sha256": "a" * 64, "origin": "speckit", "staged_executable": False}
        ],
        "created_dirs": [".specify"],
    }
    change(data)
    return data


BAD_RECORDS = {
    "not json": "{ nope",
    "unknown schema": _record_with(lambda d: d.update(schema=2)),
    "bad status": _record_with(lambda d: d.update(status="done")),
    "preview version": _record_with(lambda d: d.update(speckit_version="1.0.0rc1")),
    "unknown origin": _record_with(lambda d: d["entries"][0].update(origin="other")),
    "path outside": _record_with(lambda d: d["entries"][0].update(path="specs/x.md")),
    "copy outside": _record_with(
        lambda d: d["entries"].append(
            {"path": ".specify/x.md.new", "sha256": "b" * 64, "origin": "sdd-update", "staged_executable": False}
        )
    ),
}


@pytest.mark.parametrize("name", sorted(BAD_RECORDS))
def test_unusable_record_exit_1_and_do_not_go_online(runner, make_project, name):
    root = make_project(git=True)
    content = BAD_RECORDS[name]
    write_tree(root, {RECORD: content if isinstance(content, str) else json.dumps(content)})
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root)

    assert code == 1
    assert out == [NOT_UPDATED_BAD_RECORD]
    first = err.splitlines()[0]
    assert first.startswith("error: .specify/sdd-init.json is not a record this version of ")
    assert len(first) > len("error: .specify/sdd-init.json is not a record this version of sdd-update can use: ")
    assert "/sdd-update" in err
    assert runner.version_calls == 0 and runner.official_versions == []
    assert snap(root, with_mtime=True) == before


def test_interrupted_setup_at_the_latest_version_stops(runner, old_project):
    root = old_project()
    set_record_version(root, NEW_VERSION, "applying")
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root)

    assert code == 1
    assert out == [NOT_UPDATED_INTERRUPTED]
    assert "/sdd-init" in err
    assert runner.official_versions == []
    assert snap(root, with_mtime=True) == before


@pytest.mark.parametrize("where", ["lookup", "official", "mismatch", "copies", "record"])
def test_version_or_official_tool_failures_exit_4_and_write_nothing(runner, old_project, where):
    root = old_project()
    before = snap(root, with_mtime=True)
    before_index = index(root)
    if where == "lookup":
        runner.resolve_error = "pypi.org cannot be reached"
    elif where == "official":
        runner.official_error = "uv could not run the official tool (specify-cli 1.1.0), exit code 2"
    elif where == "mismatch":
        runner.produced_version = "1.0.5"
    elif where == "copies":
        runner.extra_output = {".specify/sdd-update/x.new": "x\n"}
    else:
        runner.extra_output = {RECORD: "{}\n"}

    code, out, err = runner.run(root)

    assert code == 4
    assert len(out) == 1
    assert out[0].startswith("Could not get the latest stable Spec Kit release: ")
    assert out[0].endswith(". Nothing was changed. Check the network connection and run /sdd-update again.")
    if where == "lookup":
        assert out == [unavailable("pypi.org cannot be reached")]
    assert "/sdd-update" in err and "retry" in err
    assert runner.version_calls == 1
    assert len(runner.official_versions) == (0 if where == "lookup" else 1)
    for dest in runner.dests:
        assert not dest.exists()
    assert snap(root, with_mtime=True) == before
    assert index(root) == before_index
    assert not (root / ".specify/sdd-update").exists()


# ============================================ US1: .sh and the index (T016)


def test_new_sh_is_staged_and_replaced_sh_is_left_in_the_index(runner, old_project):
    root = old_project()
    before_index = index(root)
    before_head = head(root)
    branch = git_run(root, "symbolic-ref", "HEAD")
    common = ".specify/scripts/bash/common.sh"
    tasks = ".specify/scripts/bash/setup-tasks.sh"
    assert before_index[common] == "100755"

    code, out, _ = runner.run(root)

    assert code == 0
    assert of(out, "staged") == [staged_line(tasks)]
    assert git_added(1) in out
    after_index = index(root)
    assert after_index[tasks] == "100755"
    assert after_index[common] == "100755"
    # The replaced .sh is not staged: the index still holds the old content.
    assert git_run(root, "diff", "--cached", "--name-only").split() == [tasks]
    assert head(root) == before_head and git_run(root, "symbolic-ref", "HEAD") == branch
    assert git_run(root, "rev-list", "--count", "HEAD").strip() == "1"
    if os.name != "nt":
        assert os.access(root / common, os.X_OK) and os.access(root / tasks, os.X_OK)
        assert not os.access(root / ".specify/scripts/bash/markdown_sections.py", os.X_OK)


def test_new_sh_is_staged_as_executable_when_git_ignores_file_modes(runner, old_project):
    root = old_project()
    git_run(root, "config", "core.fileMode", "false")
    tasks = ".specify/scripts/bash/setup-tasks.sh"

    code, out, _ = runner.run(root)

    assert code == 0
    assert of(out, "staged") == [staged_line(tasks)]
    assert index(root)[tasks] == "100755"
    assert entries(root)[tasks]["staged_executable"] is True


def test_sh_never_staged_by_sdd_init_is_staged_by_the_update(runner, sdd_init, make_project, capsys):
    # Brought in outside git, then the project became a repository: sdd-init staged nothing.
    root = make_project(git=False)
    assert init_with_version(sdd_init, root, OLD_VERSION) == 0
    capsys.readouterr()
    git_run(root, "init", "--quiet")
    git_run(root, "config", "user.name", "test")
    git_run(root, "config", "user.email", "test@example.invalid")

    code, out, _ = runner.run(root)

    assert code == 0
    expected = sorted(p for p in NEW if p.endswith(".sh"))
    assert of(out, "staged") == [staged_line(p) for p in expected]
    assert git_added(len(expected)) in out
    assert {p: m for p, m in index(root).items()} == {p: "100755" for p in expected}
    flags = {p: e["staged_executable"] for p, e in entries(root).items() if p.endswith(".sh")}
    assert flags == {p: True for p in expected}


def test_removed_sh_staged_earlier_and_not_committed_leaves_the_index(runner, sdd_init, make_project, capsys):
    root = make_project(git=True)
    old_sh = ".specify/scripts/bash/legacy.sh"

    def official_with_legacy(version, dest):
        write_versioned_official_output(Path(dest), version)
        if version == OLD_VERSION:
            write_tree(Path(dest), {old_sh: "#!/usr/bin/env bash\necho legacy\n"})

    assert init_with_version(sdd_init, root, OLD_VERSION, official_with_legacy) == 0
    capsys.readouterr()
    assert old_sh in index(root)
    assert entries(root)[old_sh]["staged_executable"] is True

    code, out, _ = runner.run(root)

    assert code == 0
    assert line("removed", old_sh) in out
    assert old_sh not in index(root)
    assert old_sh not in entries(root)


def test_staging_failure_is_a_note_and_not_a_failure(runner, old_project, monkeypatch):
    root = old_project()
    real_git = runner.shared.git

    def git_without_add(cwd, *args):
        if args and args[0] == "add":
            return subprocess.CompletedProcess(["git", *args], 128, b"", b"fatal: Unable to create index.lock\n")
        return real_git(cwd, *args)

    monkeypatch.setattr(runner.shared, "git", git_without_add)
    tasks = ".specify/scripts/bash/setup-tasks.sh"

    code, out, err = runner.run(root)

    assert code == 0
    assert of(out, "staged") == []
    assert GIT_NOTHING in out
    assert f"note: {tasks} was not added to the git index: fatal: Unable to create index.lock" in err.splitlines()
    assert entries(root)[tasks]["staged_executable"] is False


def test_outside_git_nothing_is_staged_and_no_repository_is_made(runner, old_project):
    root = old_project(git=False)

    code, out, _ = runner.run(root)

    assert code == 0
    assert of(out, "staged") == [] and of(out, "warning") == []
    assert out[-1] == GIT_NOT_A_REPO
    assert not (root / ".git").exists()


# ==================================== US1: .gitattributes and warnings (T017)


def test_missing_gitattributes_is_created(runner, sdd_init, old_project):
    root = old_project()
    (root / GITATTRIBUTES).unlink()
    commit_all(root, "no attributes")

    code, out, _ = runner.run(root)

    assert code == 0
    assert line("created", GITATTRIBUTES) in of(out, "created")
    assert (root / GITATTRIBUTES).read_bytes() == GITATTRIBUTES_BYTES
    entry = entries(root)[GITATTRIBUTES]
    assert entry["origin"] == "sdd-init" and entry["sha256"] == sha(sdd_init, GITATTRIBUTES_BYTES)
    assert f"{len(CREATED) + 1} created" in out[-2]
    assert of(out, "warning") == []


def test_existing_gitattributes_is_left_alone(runner, old_project):
    root = old_project()
    (root / GITATTRIBUTES).write_bytes(b"scripts/bash/*.sh text eol=lf\n# mine\n")
    commit_all(root, "my attributes")
    before = snap(root, with_mtime=True)[GITATTRIBUTES]

    code, out, _ = runner.run(root)

    assert code == 0
    assert GITATTRIBUTES not in "\n".join(out)
    assert snap(root, with_mtime=True)[GITATTRIBUTES] == before


def test_sh_without_an_lf_rule_is_warned_about_after_staged(runner, old_project):
    root = old_project()
    (root / GITATTRIBUTES).write_bytes(b"# no rule\n")
    commit_all(root, "no rule")

    code, out, _ = runner.run(root)

    assert code == 0
    scripts = sorted(p for p in NEW if p.endswith(".sh"))
    warnings = [
        line("warning", f"{p} has no eol=lf rule in git; it will not run after a checkout that converts line endings")
        for p in scripts
    ]
    assert of(out, "warning") == warnings
    assert out.index(warnings[0]) > out.index(of(out, "staged")[-1])
    assert out[-2].startswith("Spec Kit updated from")


# ============================== US1: failing while writing, and running again (T018)


@pytest.mark.parametrize("step", ["replace", "create", "remove"])
def test_failure_while_writing_leaves_an_applying_record_and_the_next_run_finishes(
    runner, sdd_update, sdd_init, old_project, monkeypatch, step
):
    root = old_project(git=False)
    reference = old_project(git=False)
    runner.run(reference)
    expected_record = read_record(reference)

    names = {"replace": "replace_file", "remove": "remove_file"}
    owner = sdd_init if step == "create" else sdd_update
    name = "copy_new_file" if step == "create" else names[step]
    real = getattr(owner, name)
    calls = {"n": 0}

    def failing(*args):
        calls["n"] += 1
        if calls["n"] == 2 or step == "remove":
            raise OSError("disk full")
        return real(*args)

    monkeypatch.setattr(owner, name, failing)
    runner.reset()

    code, out, err = runner.run(root)

    assert code == 1
    assert out == []
    assert "error: writing into the project failed: " in err and "disk full" in err
    assert WRITE_FAILED_HINT in err
    data = read_record(root)
    assert data["status"] == "applying" and data["speckit_version"] == OLD_VERSION
    paths = {e["path"] for e in data["entries"]}
    assert set(OLD) | set(CREATED) | {GITATTRIBUTES} <= paths
    # No file is left half written: each one is either the old or the new version.
    for path in UPDATED:
        assert (root / path).read_bytes() in (OLD[path].encode(), NEW[path].encode()), path
    still_old = [p for p in UPDATED if (root / p).read_bytes() == OLD[p].encode()]

    monkeypatch.setattr(owner, name, real)
    runner.reset()

    code, out, err = runner.run(root)

    assert code == 0, err
    assert read_record(root) == expected_record
    for path in UPDATED + CREATED:
        assert (root / path).read_bytes() == NEW[path].encode()
    for path in REMOVED:
        assert not (root / path).exists()
    assert not [k for k in snap(root) if k.endswith(".sdd-update-tmp")]
    # Only what this run did is reported.
    assert [l.split()[1] for l in of(out, "updated")] == still_old
    code, out, _ = runner.run(root)
    assert out == [already()]


def test_a_replaced_file_is_not_reported_again_by_the_next_run(runner, sdd_update, old_project, monkeypatch):
    root = old_project(git=False)
    real = sdd_update.replace_file
    calls = {"n": 0}

    def failing(source, target):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full")
        return real(source, target)

    monkeypatch.setattr(sdd_update, "replace_file", failing)
    code, _, _ = runner.run(root)
    assert code == 1
    replaced = [p for p in UPDATED if (root / p).read_bytes() == NEW[p].encode()]
    assert len(replaced) == 2

    monkeypatch.setattr(sdd_update, "replace_file", real)
    code, out, _ = runner.run(root)

    assert code == 0
    assert [l.split()[1] for l in of(out, "updated")] == [p for p in UPDATED if p not in replaced]
    assert out[-2] == summary(OLD_VERSION, NEW_VERSION, len(UPDATED) - 2, 0, len(REMOVED), 0)


def test_replacing_writes_a_temporary_file_and_swaps_it_in(sdd_update, tmp_path, monkeypatch):
    source = tmp_path / "new.sh"
    source.write_bytes(b"new\n")
    os.chmod(source, 0o755)
    target = tmp_path / "dir" / "old.sh"
    target.parent.mkdir()
    target.write_bytes(b"old\n")
    os.chmod(target, 0o644)
    seen = []
    real_replace = os.replace

    def watching(src, dst):
        seen.append((Path(src).name, Path(dst).name, Path(src).read_bytes()))
        return real_replace(src, dst)

    monkeypatch.setattr(sdd_update.os, "replace", watching)

    sdd_update.replace_file(source, target)

    assert seen == [("old.sh.sdd-update-tmp", "old.sh", b"new\n")]
    assert target.read_bytes() == b"new\n"
    assert sorted(p.name for p in target.parent.iterdir()) == ["old.sh"]
    if os.name != "nt":
        assert os.access(target, os.X_OK)


def test_applying_record_older_than_the_latest_is_updated_like_a_complete_one(runner, old_project):
    root = old_project()
    set_record_version(root, OLD_VERSION, "applying")
    reference = old_project()

    code, out, _ = runner.run(root)
    code_ref, out_ref, _ = runner.run(reference)

    assert code == code_ref == 0
    assert out == out_ref
    assert read_record(root) == read_record(reference)


def test_a_file_changed_while_an_update_was_interrupted_is_never_written(runner, sdd_update, old_project, monkeypatch):
    root = old_project(git=False)
    real = sdd_update.replace_file

    def failing(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(sdd_update, "replace_file", failing)
    assert runner.run(root)[0] == 1
    changed = ".specify/templates/plan-template.md"
    (root / changed).write_bytes(b"my plan\n")
    monkeypatch.setattr(sdd_update, "replace_file", real)

    code, out, _ = runner.run(root)

    assert code == 0
    assert (root / changed).read_bytes() == b"my plan\n"
    assert kept_modified(changed) in out


# ================================================ US2: modified files are kept (T030)

PLAN = ".specify/templates/plan-template.md"
COMMON = ".specify/scripts/bash/common.sh"
LEGACY = ".claude/skills/speckit-legacy/SKILL.md"
SPECIFY_SKILL = ".claude/skills/speckit-specify/SKILL.md"


def test_modified_files_are_kept_with_a_comparison_copy(runner, sdd_init, old_project):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    (root / COMMON).write_bytes(b"#!/usr/bin/env bash\necho mine\n")
    commit_all(root, "my changes")
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root)

    assert code == 0, err
    updated = [p for p in UPDATED if p not in (PLAN, COMMON)]
    sh_created = [p for p in CREATED if p.endswith(".sh")]
    assert out == (
        [line("updated", p) for p in updated]
        + [line("created", p) for p in CREATED]
        + [line("removed", p) for p in REMOVED]
        + [kept_modified(COMMON), kept_modified(PLAN)]
        + [staged_line(p) for p in sh_created]
        + [
            summary(OLD_VERSION, NEW_VERSION, len(updated), len(CREATED), len(REMOVED), 2),
            git_added(len(sh_created)),
            NEXT,
        ]
    )
    after = snap(root, with_mtime=True)
    record = entries(root)
    for path in (PLAN, COMMON):
        assert after[path] == before[path], path
        copy = copy_of(path)
        assert (root / copy).read_bytes() == NEW[path].encode()
        assert record[copy] == {
            "path": copy,
            "sha256": sha(sdd_init, NEW[path]),
            "origin": "sdd-update",
            "staged_executable": False,
        }
        assert record[path]["sha256"] == sha(sdd_init, NEW[path])
        assert copy not in index(root)
        if os.name != "nt":
            assert not os.access(root / copy, os.X_OK)
    assert index(root)[COMMON] == "100755"
    assert git_run(root, "diff", "--cached", "--name-only").split() == sh_created
    dirs = read_record(root)["created_dirs"]
    for directory in (".specify/sdd-update", ".specify/sdd-update/.specify", ".specify/sdd-update/.specify/templates"):
        assert directory in dirs
    # Still modified afterwards: a later update keeps it again.
    assert sha(sdd_init, (root / PLAN).read_bytes()) != record[PLAN]["sha256"]


def test_kept_lines_are_sorted_by_path_across_the_three_kinds(runner, old_project, make_project, sdd_init, capsys):
    root = make_project(git=True)
    write_tree(root, {SPECIFY_SKILL: "mine before sdd-init\n"})
    assert init_with_version(sdd_init, root, OLD_VERSION) == 0
    capsys.readouterr()
    (root / PLAN).write_bytes(b"# my plan\n")
    (root / LEGACY).write_bytes(b"my legacy\n")

    code, out, _ = runner.run(root)

    assert code == 0
    assert of(out, "kept") == [kept_orphan(LEGACY), kept_foreign(SPECIFY_SKILL), kept_modified(PLAN)]


# ================================ US2: not from sdd-init, and no longer provided (T031)


def test_files_not_created_by_sdd_init_are_kept_and_never_recorded(runner, sdd_init, make_project, capsys):
    root = make_project(git=True)
    write_tree(
        root,
        {
            PLAN: "# their plan\n",  # differs from the new version
            SPECIFY_SKILL: NEW[SPECIFY_SKILL],  # already the new version
            ".specify/templates/spec-template.md": NEW[".specify/templates/spec-template.md"],
        },
    )
    assert init_with_version(sdd_init, root, OLD_VERSION) == 0
    capsys.readouterr()
    assert PLAN not in entries(root) and SPECIFY_SKILL not in entries(root)
    commit_all(root, "init")
    before = snap(root, with_mtime=True)

    code, out, _ = runner.run(root)

    assert code == 0
    assert of(out, "kept") == [kept_foreign(PLAN)]
    assert SPECIFY_SKILL not in "\n".join(out)
    assert ".specify/templates/spec-template.md" not in "\n".join(out)
    after = snap(root, with_mtime=True)
    for path in (PLAN, SPECIFY_SKILL, ".specify/templates/spec-template.md"):
        assert after[path] == before[path]
    record = entries(root)
    assert PLAN not in record and SPECIFY_SKILL not in record and ".specify/templates/spec-template.md" not in record
    assert (root / copy_of(PLAN)).read_bytes() == NEW[PLAN].encode()
    assert record[copy_of(PLAN)]["origin"] == "sdd-update"
    assert out[-1] == NEXT


def test_modified_file_no_longer_provided_is_kept_and_forgotten(runner, old_project):
    root = old_project()
    (root / LEGACY).write_bytes(b"my legacy skill\n")

    code, out, _ = runner.run(root)

    assert code == 0
    assert of(out, "kept") == [kept_orphan(LEGACY)]
    assert of(out, "removed") == []
    assert (root / LEGACY).read_bytes() == b"my legacy skill\n"
    assert LEGACY not in entries(root)
    assert not (root / copy_of(LEGACY)).exists()
    assert not any(l.startswith("Next:") for l in out)
    assert out[-2] == summary(OLD_VERSION, NEW_VERSION, len(UPDATED), len(CREATED), 0, 1)


def test_file_no_longer_provided_and_already_gone_is_only_forgotten(runner, old_project):
    root = old_project()
    (root / LEGACY).unlink()

    code, out, _ = runner.run(root)

    assert code == 0
    assert LEGACY not in "\n".join(out)
    assert LEGACY not in entries(root)
    assert out[-2] == summary(OLD_VERSION, NEW_VERSION, len(UPDATED), len(CREATED), 0, 0)


def test_spec_kit_file_deleted_by_the_maintainer_is_created_again(runner, sdd_init, old_project):
    root = old_project()
    (root / PLAN).unlink()
    (root / ".specify/templates/spec-template.md").unlink()

    code, out, _ = runner.run(root)

    assert code == 0
    assert line("created", PLAN) in out and line("created", ".specify/templates/spec-template.md") in out
    assert (root / PLAN).read_bytes() == NEW[PLAN].encode()
    assert entries(root)[PLAN]["sha256"] == sha(sdd_init, NEW[PLAN])


def test_files_neither_recorded_nor_provided_are_not_looked_at(runner, old_project):
    root = old_project()
    mine = {
        ".specify/extensions/mine.md": "mine\n",
        ".claude/skills/speckit-mine/SKILL.md": "my skill\n",
        ".claude/settings.json": "{}\n",
    }
    write_tree(root, mine)
    before = snap(root, with_mtime=True)

    code, out, _ = runner.run(root)

    assert code == 0
    after = snap(root, with_mtime=True)
    for path in mine:
        assert after[path] == before[path]
        assert path not in "\n".join(out)
        assert path not in entries(root)


def test_a_directory_in_place_of_a_file_counts_as_modified(runner, old_project):
    root = old_project()
    (root / PLAN).unlink()
    (root / PLAN).mkdir()
    write_tree(root, {PLAN + "/inside.md": "x\n"})

    code, out, _ = runner.run(root)

    assert code == 0
    assert kept_modified(PLAN) in out
    assert (root / PLAN / "inside.md").read_bytes() == b"x\n"


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need extra rights on Windows")
def test_a_symbolic_link_in_place_of_a_file_counts_as_modified(runner, old_project, tmp_path):
    root = old_project()
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_bytes(OLD[PLAN].encode())
    (root / PLAN).unlink()
    os.symlink(elsewhere, root / PLAN)

    code, out, _ = runner.run(root)

    assert code == 0
    assert kept_modified(PLAN) in out
    assert os.path.islink(root / PLAN)
    assert elsewhere.read_bytes() == OLD[PLAN].encode()


def test_sdd_init_right_before_sdd_update_reports_the_latest_release(runner, sdd_init, make_project, capsys):
    # Spec Kit files that sdd-init did not create; sdd-init records the version that is latest at that moment.
    root = make_project(git=True)
    write_versioned_official_output(root, OLD_VERSION)
    assert init_with_version(sdd_init, root, NEW_VERSION) == 0
    capsys.readouterr()
    before = snap(root, with_mtime=True)

    code, out, _ = runner.run(root)

    assert code == 0
    assert out == [already()]
    assert runner.official_versions == []
    assert snap(root, with_mtime=True) == before


# ======================== US2: project content and comparison copies (T032)


@pytest.mark.parametrize("constitution", ["written", "blank"])
def test_memory_and_specs_are_never_touched(runner, old_project, constitution):
    root = old_project()
    if constitution == "written":
        (root / ".specify/memory/constitution.md").write_bytes(b"# Our constitution\n\nreal principles\n")
    write_tree(root, {"specs/001-a/spec.md": "# a\n", "specs/001-a/plan.md": "# plan a\n", "specs/002-b/spec.md": "# b\n"})
    commit_all(root, "content")
    before = snap(root, with_mtime=True)
    memory_entries = {p: e for p, e in entries(root).items() if p.startswith(PROTECTED)}
    assert ".specify/memory/.constitution-template.json" in memory_entries

    code, out, _ = runner.run(root)

    assert code == 0
    after = snap(root, with_mtime=True)
    for key in before:
        if key.startswith(PROTECTED) or key.startswith("specs/"):
            assert after[key] == before[key], key
    assert not [k for k in after if k.startswith(PROTECTED) and k not in before]
    assert ".specify/memory" not in "\n".join(out)
    assert {p: e for p, e in entries(root).items() if p.startswith(PROTECTED)} == memory_entries
    assert not (root / ".specify/sdd-update/.specify/memory").exists()


def test_copies_from_the_previous_update_are_replaced_by_the_next_one(runner, sdd_init, old_project):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    (root / SPECIFY_SKILL).write_bytes(b"my specify\n")
    runner.run(root)
    commit_all(root, "updated")
    # The maintainer scribbles in one copy and merges the other file.
    (root / copy_of(PLAN)).write_bytes(b"notes in the copy\n")
    (root / SPECIFY_SKILL).write_bytes(NEW[SPECIFY_SKILL].encode())
    runner.latest = "1.2.0"

    code, out, _ = runner.run(root)

    assert code == 0
    assert of(out, "kept") == [kept_modified(PLAN)]
    assert (root / copy_of(PLAN)).read_bytes() == NEW[PLAN].encode()
    assert not (root / copy_of(SPECIFY_SKILL)).exists()
    assert not (root / ".specify/sdd-update/.claude").exists()
    record = entries(root)
    assert copy_of(SPECIFY_SKILL) not in record
    assert record[copy_of(PLAN)]["sha256"] == sha(sdd_init, NEW[PLAN])
    assert ".specify/sdd-update/.claude" not in read_record(root)["created_dirs"]
    assert out[-1] == NEXT


def test_copies_deleted_by_the_maintainer_do_not_break_the_next_update(runner, old_project):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    runner.run(root)
    shutil.rmtree(root / ".specify/sdd-update")
    runner.latest = "1.2.0"

    code, out, err = runner.run(root)

    assert code == 0, err
    assert of(out, "kept") == [kept_modified(PLAN)]
    assert (root / copy_of(PLAN)).read_bytes() == NEW[PLAN].encode()


@pytest.mark.parametrize("blocker", ["copy", "parent of a copy", "parent of a new file"])
def test_something_in_the_way_stops_before_writing(runner, old_project, blocker):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    if blocker == "copy":
        write_tree(root, {copy_of(PLAN): "someone else's\n"})
        expected = copy_of(PLAN)
    elif blocker == "parent of a copy":
        write_tree(root, {".specify/sdd-update/.specify": "a file\n"})
        expected = ".specify/sdd-update/.specify"
    else:
        runner.extra_output = {".claude/skills/speckit-newone/SKILL.md": "new\n"}
        write_tree(root, {".claude/skills/speckit-newone": "a file\n", copy_of(PLAN): "also in the way\n"})
        expected = ".claude/skills/speckit-newone"
    commit_all(root, "blocked")
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root)

    assert code == 1
    assert out == [
        f"Spec Kit was not updated: {expected} is in the way. Nothing was changed. Move it away and run /sdd-update again."
    ]
    assert expected in err
    assert snap(root, with_mtime=True) == before
    assert status(root) == ""


# ========================== US2: already the latest, with copies still to merge (T033)


def test_already_latest_lists_kept_files_that_still_differ(runner, old_project):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    (root / COMMON).write_bytes(b"#!/usr/bin/env bash\necho mine\n")
    runner.run(root)
    before = snap(root, with_mtime=True)
    before_index, before_status = git_run(root, "ls-files", "-s"), status(root)

    for attempt in range(3):
        runner.reset()
        code, out, err = runner.run(root)

        assert code == 0
        assert out == [kept_pending(COMMON), kept_pending(PLAN), already(), NEXT], attempt
        assert runner.official_versions == []
        assert snap(root, with_mtime=True) == before
        assert git_run(root, "ls-files", "-s") == before_index and status(root) == before_status


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_a_merged_file_is_no_longer_listed(runner, old_project, newline):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    (root / COMMON).write_bytes(b"#!/usr/bin/env bash\necho mine\n")
    runner.run(root)
    (root / PLAN).write_bytes((root / copy_of(PLAN)).read_bytes().replace(b"\n", newline))
    before = snap(root, with_mtime=True)

    code, out, _ = runner.run(root)

    assert code == 0
    assert out == [kept_pending(COMMON), already(), NEXT]
    assert snap(root, with_mtime=True) == before
    assert (root / copy_of(PLAN)).exists()  # not cleaned up while nothing is updated

    (root / COMMON).write_bytes((root / copy_of(COMMON)).read_bytes())
    code, out, _ = runner.run(root)
    assert out == [already()]


@pytest.mark.parametrize("gone", ["copy", "file"])
def test_missing_copy_or_missing_file_is_not_listed(runner, old_project, gone):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    runner.run(root)
    (root / (copy_of(PLAN) if gone == "copy" else PLAN)).unlink()

    code, out, _ = runner.run(root)

    assert code == 0
    assert out == [already()]


def test_copies_are_untracked_and_no_ignore_rule_is_written(runner, old_project):
    root = old_project()
    (root / PLAN).write_bytes(b"# my plan\n")
    ignores_before = {k: v for k, v in snap(root).items() if k.endswith(".gitignore") or k.endswith("exclude")}
    exclude_before = (root / ".git/info/exclude").read_bytes() if (root / ".git/info/exclude").exists() else None

    runner.run(root)

    assert f"?? {copy_of(PLAN)}" in status(root).splitlines()
    assert copy_of(PLAN) not in index(root)
    assert {k: v for k, v in snap(root).items() if k.endswith(".gitignore") or k.endswith("exclude")} == ignores_before
    after_exclude = (root / ".git/info/exclude").read_bytes() if (root / ".git/info/exclude").exists() else None
    assert after_exclude == exclude_before


# ========================================== US2: the same on both platforms (T034)


def to_crlf(root: Path) -> None:
    """Rewrite every text file of the project with CRLF, as a Windows checkout with autocrlf would."""
    for path in root.rglob("*"):
        if ".git" in path.relative_to(root).parts or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" not in data:
            path.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


def test_crlf_files_are_judged_like_lf_files(runner, old_project):
    lf, crlf = old_project(git=False), old_project(git=False)
    for root in (lf, crlf):
        (root / PLAN).write_bytes(b"# my plan\n")
    to_crlf(crlf)

    code_lf, out_lf, _ = runner.run(lf)
    code_crlf, out_crlf, _ = runner.run(crlf)

    assert code_lf == code_crlf == 0
    assert out_crlf == out_lf
    assert of(out_lf, "kept") == [kept_modified(PLAN)]
    assert len(of(out_lf, "updated")) == len(UPDATED) - 1


@pytest.mark.parametrize("git", [True, False])
def test_output_and_record_do_not_depend_on_the_directory(runner, old_project, git):
    first, second = old_project(git=git), old_project(git=git)
    for root in (first, second):
        (root / PLAN).write_bytes(b"# my plan\n")

    _, out_first, _ = runner.run(first)
    _, out_second, _ = runner.run(second)

    assert out_first == out_second
    assert (first / RECORD).read_bytes() == (second / RECORD).read_bytes()
    assert "\\" not in "\n".join(out_first)
    assert b"\\" not in (first / RECORD).read_bytes()


# ============= plan.md trade-off 10: a new release between an interrupted update and the next run


def test_files_replaced_before_an_interruption_are_kept_if_a_newer_release_appears(runner, sdd_update, old_project, monkeypatch):
    root = old_project(git=False)
    real = sdd_update.replace_file
    calls = {"n": 0}

    def failing(source, target):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real(source, target)

    monkeypatch.setattr(sdd_update, "replace_file", failing)
    assert runner.run(root)[0] == 1
    replaced = [p for p in UPDATED if (root / p).read_bytes() == NEW[p].encode()]
    assert len(replaced) == 1
    monkeypatch.setattr(sdd_update, "replace_file", real)

    # 1.2.0 changes every file again.
    def official_120(version, dest):
        write_versioned_official_output(Path(dest), version)
        for path in UPDATED:
            if path != ".specify/init-options.json":
                (Path(dest) / path).write_bytes(NEW[path].encode() + b"# 1.2.0\n")

    monkeypatch.setattr(runner, "official", official_120)
    runner.latest = "1.2.0"

    code, out, _ = runner.run(root)

    # Safe, but the file replaced by the interrupted run now needs a manual comparison.
    assert code == 0
    assert of(out, "kept") == [kept_modified(p) for p in replaced]
    assert (root / replaced[0]).read_bytes() == NEW[replaced[0]].encode()
    assert out[0].startswith("updated ") and out[-1] == NEXT


# ============= Edge Case: an interruption while kept files exist, then running again (T048)


@pytest.mark.parametrize(
    "where, prior",
    [
        ("write_copy", False),
        ("replace_file", False),
        ("write_copy", True),
    ],
    ids=["second-copy", "replace", "after-old-copies-deleted"],
)
def test_interruption_with_kept_files_then_running_again_loses_nothing(
    runner, sdd_update, old_project, monkeypatch, where, prior
):
    mine = {PLAN: b"# my plan\n", SPECIFY_SKILL: b"my specify\n"}

    def prepare(root):
        for path, data in mine.items():
            (root / path).write_bytes(data)
        if prior:
            assert runner.run(root)[0] == 0
            commit_all(root, "updated")
            runner.latest = "1.2.0"

    reference = old_project()
    prepare(reference)
    runner.reset()
    code, ref_out, err = runner.run(reference)
    assert code == 0, err
    ref_snap = snap(reference)
    ref_record = (reference / RECORD).read_bytes()

    root = old_project()
    runner.latest = NEW_VERSION
    prepare(root)
    real = getattr(sdd_update, where)
    calls = {"n": 0}
    # Fail on the second copy written, the first file replaced, or the first copy written after the old ones went.
    fail_at = 2 if (where == "write_copy" and not prior) else 1

    def failing(*args):
        calls["n"] += 1
        if calls["n"] == fail_at:
            raise OSError("disk full")
        return real(*args)

    monkeypatch.setattr(sdd_update, where, failing)
    runner.reset()

    code, out, err = runner.run(root)

    assert code == 1
    assert out == []
    assert "disk full" in err
    assert read_record(root)["status"] == "applying"
    for path, data in mine.items():
        assert (root / path).read_bytes() == data, path

    monkeypatch.setattr(sdd_update, where, real)
    runner.reset()

    code, out, err = runner.run(root)

    assert code == 0, err
    for path, data in mine.items():
        assert (root / path).read_bytes() == data, path
        assert (root / copy_of(path)).read_bytes() == NEW[path].encode(), path
    assert of(out, "kept") == of(ref_out, "kept")
    assert (root / RECORD).read_bytes() == ref_record
    assert snap(root) == ref_snap
    assert not [k for k in snap(root) if k.endswith(".sdd-update-tmp")]
    names = [e["path"] for e in read_record(root)["entries"]]
    assert len(names) == len(set(names))
