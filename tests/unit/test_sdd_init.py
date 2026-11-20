"""Unit tests for home/skills/sdd-init/scripts/sdd_init.py.

The official tool is replaced by a fake that writes a small file tree, and the
version lookup by a function that returns a fixed version, so nothing here
needs the network. Contracts: specs/003-sdd-init/contracts/cli.md and
specs/003-sdd-init/data-model.md.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import (
    FAKE_VERSION,
    fake_official_files,
    git_run,
    snapshot,
    write_fake_official_output,
    write_tree,
)

RECORD = ".specify/sdd-init.json"
GITATTRIBUTES = ".specify/.gitattributes"
GITATTRIBUTES_BYTES = b"scripts/bash/*.sh text eol=lf\n"
NEXT_LINES = [
    "Next: run /sdd-grill to be questioned until the constitution and specs are decided.",
    "Or use Spec Kit directly: run /speckit-constitution, then /speckit-specify.",
]
GIT_NOT_A_REPO = (
    "Git: not a git repository, and none was created. Executable bits cannot be recorded "
    "until the files are added with: git add --chmod=+x .specify/scripts/bash/*.sh"
)
WARNING_LINE = (
    "warning   .specify/.gitattributes was not created by sdd-init; "
    "add this line to it: scripts/bash/*.sh text eol=lf"
)
NOTHING_TO_REMOVE = (
    "Nothing to remove: this project has no sdd-init record, "
    "so no file can be proven to be created by sdd-init."
)
NOTHING_REMOVED = (
    "Nothing was removed: .specify/sdd-init.json cannot be read, "
    "so no file can be proven to be created by sdd-init."
)

OFFICIAL = sorted(fake_official_files())
OFFICIAL_SH = [p for p in OFFICIAL if p.endswith(".sh")]
ALL_CREATED = sorted(OFFICIAL + [GITATTRIBUTES])


def line(action: str, rest: str) -> str:
    return f"{action:<10}{rest}"


def snap(root: Path, with_mtime: bool = False) -> dict:
    """Snapshot of the project without git's own directory."""
    return {
        k: v
        for k, v in snapshot(root, with_mtime=with_mtime).items()
        if k != ".git/" and not k.startswith(".git/")
    }


def read_record(root: Path) -> dict:
    return json.loads((root / RECORD).read_bytes().decode("utf-8"))


def entry_paths(root: Path) -> list[str]:
    return [e["path"] for e in read_record(root)["entries"]]


def index(root: Path) -> dict[str, str]:
    """Map every path in the git index to its mode."""
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


def commit_count(root: Path) -> int:
    done = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root, capture_output=True)
    return int(done.stdout.decode().strip()) if done.returncode == 0 else 0


class Runner:
    """Runs main() in-process with replaceable steps and records how they were used."""

    def __init__(self, module, capsys, monkeypatch):
        self.module = module
        self.capsys = capsys
        self.monkeypatch = monkeypatch
        self.latest = FAKE_VERSION
        self.version_calls = 0
        self.official_versions: list[str] = []
        self.dests: list[Path] = []
        self.resolve_error: str | None = None
        self.official_error: str | None = None
        self.produced_version: str | None = None

    def resolve(self) -> str:
        self.version_calls += 1
        if self.resolve_error:
            raise self.module.StepFailed(self.resolve_error)
        return self.latest

    def official(self, version: str, dest: Path) -> None:
        self.official_versions.append(version)
        self.dests.append(Path(dest))
        assert list(Path(dest).iterdir()) == [], "the official tool must run in an empty directory"
        if self.official_error:
            raise self.module.StepFailed(self.official_error)
        write_fake_official_output(Path(dest), self.produced_version or version)

    def run(self, root: Path, *args: str) -> tuple[int, list[str], str]:
        self.monkeypatch.chdir(root)
        self.capsys.readouterr()
        code = self.module.main(list(args), resolve_version=self.resolve, run_official=self.official)
        captured = self.capsys.readouterr()
        return code, captured.out.splitlines(), captured.err


@pytest.fixture
def runner(sdd_init, capsys, monkeypatch):
    return Runner(sdd_init, capsys, monkeypatch)


def of(lines: list[str], action: str) -> list[str]:
    return [l for l in lines if l.split(" ", 1)[0] == action]


# ===================================================================== core


@pytest.mark.parametrize("argv", [[], ["install"], ["init", "extra"], ["--help"], ["remove", "-f"]])
def test_bad_arguments_exit_1_and_show_usage(runner, make_project, argv):
    root = make_project(git=False)

    code, out, err = runner.run(root, *argv)

    assert code == 1
    assert "usage" in err.lower()
    assert "init" in err and "remove" in err
    assert snap(root) == {}
    assert runner.version_calls == 0 and runner.official_versions == []


def test_project_root_is_the_top_of_the_git_work_tree(sdd_init, make_project):
    root = make_project(git=True)
    sub = root / "a" / "b"
    sub.mkdir(parents=True)

    assert os.path.samefile(sdd_init.find_project_root(sub), root)
    assert os.path.samefile(sdd_init.find_project_root(root), root)


def test_project_root_is_the_current_directory_outside_git(sdd_init, make_project):
    root = make_project(git=False)
    sub = root / "a"
    sub.mkdir()

    assert os.path.samefile(sdd_init.find_project_root(sub), sub)


def test_content_hash_ignores_crlf_but_nothing_else(sdd_init):
    lf = b"line one\nline two\n"
    crlf = b"line one\r\nline two\r\n"

    assert sdd_init.content_hash(lf) == sdd_init.content_hash(crlf)
    assert len(sdd_init.content_hash(lf)) == 64
    assert sdd_init.content_hash(lf) == sdd_init.content_hash(lf).lower()
    assert sdd_init.content_hash(lf) != sdd_init.content_hash(b"line one\nline two")
    assert sdd_init.content_hash(lf) != sdd_init.content_hash(b"line one\nline  two\n")
    assert sdd_init.content_hash(lf) != sdd_init.content_hash(b"line one\rline two\r")


def make_record(sdd_init, **changes):
    entries = [
        sdd_init.Entry(".specify/templates/b.md", "b" * 64, "speckit", False),
        sdd_init.Entry(".claude/skills/speckit-plan/SKILL.md", "a" * 64, "speckit", False),
        sdd_init.Entry(".specify/.gitattributes", "c" * 64, "sdd-init", False),
        sdd_init.Entry(".specify/scripts/bash/x.sh", "d" * 64, "speckit", True),
    ]
    values = dict(
        status="complete",
        speckit_version="1.4.3",
        entries=entries,
        created_dirs=[".specify/templates", ".specify", ".claude"],
    )
    values.update(changes)
    return sdd_init.Record(**values)


def test_record_round_trip_and_stable_bytes(sdd_init, tmp_path):
    record = make_record(sdd_init)

    sdd_init.write_record(tmp_path, record)
    data = (tmp_path / RECORD).read_bytes()
    loaded = sdd_init.load_record(tmp_path)

    assert b"\r" not in data
    assert data.endswith(b"\n")
    text = data.decode("utf-8")
    pairs = json.loads(text, object_pairs_hook=list)
    assert [k for k, _ in pairs] == [
        "schema",
        "status",
        "speckit_version",
        "init_options",
        "entries",
        "created_dirs",
    ]
    parsed = json.loads(text)
    assert parsed["schema"] == 1
    assert parsed["init_options"] == {"integration": "claude", "script": "sh"}
    assert [list(e) for e in parsed["entries"]] == [["path", "sha256", "origin", "staged_executable"]] * 4
    paths = [e["path"] for e in parsed["entries"]]
    assert paths == sorted(paths)
    assert parsed["created_dirs"] == sorted(parsed["created_dirs"])
    assert str(tmp_path) not in text and "\\" not in text

    assert loaded.status == "complete"
    assert loaded.speckit_version == "1.4.3"
    assert [e.path for e in loaded.entries] == paths
    assert {e.path: e for e in loaded.entries}[".specify/scripts/bash/x.sh"].staged_executable is True
    # Writing what was read gives the same bytes.
    sdd_init.write_record(tmp_path, loaded)
    assert (tmp_path / RECORD).read_bytes() == data


def test_record_missing_is_not_the_same_as_invalid(sdd_init, tmp_path):
    assert sdd_init.load_record(tmp_path) is None


def valid_record_dict() -> dict:
    return {
        "schema": 1,
        "status": "complete",
        "speckit_version": "1.4.3",
        "init_options": {"integration": "claude", "script": "sh"},
        "entries": [
            {
                "path": ".specify/templates/a.md",
                "sha256": "a" * 64,
                "origin": "speckit",
                "staged_executable": False,
            }
        ],
        "created_dirs": [".specify", ".specify/templates"],
    }


def write_raw_record(root: Path, content) -> None:
    if not isinstance(content, (bytes, str)):
        content = json.dumps(content)
    write_tree(root, {RECORD: content})


def with_path(path: str) -> dict:
    data = valid_record_dict()
    data["entries"][0]["path"] = path
    return data


UNREADABLE_RECORDS = {
    "not json": "{ this is not json",
    "not an object": "[1, 2]",
    "unknown schema": {**valid_record_dict(), "schema": 2},
    "schema missing": {k: v for k, v in valid_record_dict().items() if k != "schema"},
    "other tool": {"version": "1.2.6", "files": {"a": "b"}},
    "bad status": {**valid_record_dict(), "status": "done"},
}

BAD_PATH_RECORDS = {
    "specs": with_path("specs/x.md"),
    "parent": with_path("../x"),
    "escape": with_path(".specify/../specs/x.md"),
    "absolute": with_path("/etc/passwd"),
    "backslash": with_path(".specify\\templates\\a.md"),
    "other skill": with_path(".claude/skills/mine/SKILL.md"),
    "claude root": with_path(".claude/settings.json"),
    "created dir": {**valid_record_dict(), "created_dirs": ["specs"]},
}


@pytest.mark.parametrize("name", sorted(UNREADABLE_RECORDS))
def test_unreadable_records_are_invalid(sdd_init, tmp_path, name):
    write_raw_record(tmp_path, UNREADABLE_RECORDS[name])

    with pytest.raises(sdd_init.InvalidRecord) as info:
        sdd_init.load_record(tmp_path)

    assert info.value.kind == "unreadable"


@pytest.mark.parametrize("name", sorted(BAD_PATH_RECORDS))
def test_records_with_paths_outside_spec_kit_are_invalid(sdd_init, tmp_path, name):
    write_raw_record(tmp_path, BAD_PATH_RECORDS[name])

    with pytest.raises(sdd_init.InvalidRecord) as info:
        sdd_init.load_record(tmp_path)

    assert info.value.kind == "paths"


def test_valid_record_dict_loads(sdd_init, tmp_path):
    write_raw_record(tmp_path, valid_record_dict())

    assert sdd_init.load_record(tmp_path).speckit_version == "1.4.3"


# ============================================================ US1: version


def release_file(yanked: bool = False) -> dict:
    return {"filename": "specify_cli.whl", "yanked": yanked}


def test_pick_latest_stable_takes_the_largest_by_number(sdd_init):
    releases = {v: [release_file()] for v in ["1.9.0", "1.10.0", "1.2.6", "0.99.99"]}

    assert sdd_init.pick_latest_stable(releases) == "1.10.0"


@pytest.mark.parametrize("suffix", ["a1", "b2", "rc1", ".dev3", ".post1"])
def test_pick_latest_stable_excludes_previews(sdd_init, suffix):
    releases = {"1.4.3": [release_file()], "2.0.0" + suffix: [release_file()]}

    assert sdd_init.pick_latest_stable(releases) == "1.4.3"


def test_pick_latest_stable_excludes_yanked_and_empty_releases(sdd_init):
    releases = {
        "1.4.3": [release_file(), release_file(yanked=True)],
        "1.5.0": [release_file(yanked=True), release_file(yanked=True)],
        "1.6.0": [],
    }

    assert sdd_init.pick_latest_stable(releases) == "1.4.3"


def test_pick_latest_stable_without_a_candidate_fails(sdd_init):
    assert sdd_init.pick_latest_stable({}) is None
    assert sdd_init.pick_latest_stable({"1.0.0rc1": [release_file()], "1.0.0": []}) is None


# ========================================================= US1: fresh init


def test_fresh_init_outside_git(runner, make_project):
    root = make_project(git=False)

    code, out, err = runner.run(root, "init")

    assert code == 0
    files = fake_official_files()
    for rel, content in files.items():
        assert (root / rel).read_bytes() == content.encode("utf-8")
    assert of(out, "created") == [line("created", p) for p in ALL_CREATED]
    assert of(out, "skipped") == [] and of(out, "staged") == [] and of(out, "warning") == []
    assert out[-4:] == [
        f"Spec Kit {FAKE_VERSION} initialized: {len(ALL_CREATED)} created, 0 skipped.",
        GIT_NOT_A_REPO,
        *NEXT_LINES,
    ]
    assert len(out) == len(ALL_CREATED) + 4
    assert not (root / ".git").exists()

    record = read_record(root)
    assert record["status"] == "complete"
    assert record["speckit_version"] == FAKE_VERSION
    assert record["init_options"] == {"integration": "claude", "script": "sh"}
    assert [e["path"] for e in record["entries"]] == ALL_CREATED
    assert RECORD not in [e["path"] for e in record["entries"]]
    origins = {e["path"]: e["origin"] for e in record["entries"]}
    assert all(origins[p] == "speckit" for p in OFFICIAL)
    assert all(e["staged_executable"] is False for e in record["entries"])
    assert record["created_dirs"] == [
        ".claude",
        ".claude/skills",
        ".claude/skills/speckit-plan",
        ".claude/skills/speckit-specify",
        ".specify",
        ".specify/memory",
        ".specify/scripts",
        ".specify/scripts/bash",
        ".specify/templates",
    ]

    assert runner.version_calls == 1
    assert runner.official_versions == [FAKE_VERSION]
    assert not runner.dests[0].exists()
    assert root not in runner.dests[0].parents and runner.dests[0] != root


def test_fresh_init_records_hashes_of_the_content(runner, sdd_init, make_project):
    root = make_project(git=False)

    runner.run(root, "init")

    for entry in read_record(root)["entries"]:
        assert entry["sha256"] == sdd_init.content_hash((root / entry["path"]).read_bytes())


def test_created_dirs_only_lists_directories_made_by_this_run(runner, make_project):
    root = make_project(git=False)
    (root / ".claude" / "skills").mkdir(parents=True)
    write_tree(root, {".specify/templates/mine.md": "x"})

    runner.run(root, "init")

    dirs = read_record(root)["created_dirs"]
    assert ".claude" not in dirs and ".claude/skills" not in dirs
    assert ".specify" not in dirs and ".specify/templates" not in dirs
    assert ".claude/skills/speckit-plan" in dirs and ".specify/memory" in dirs


def test_fresh_init_in_git_does_not_commit_or_switch_branch(runner, make_project):
    root = make_project(git=True)
    write_tree(root, {"README.md": "hello\n"})
    commit_all(root, "first")
    head = git_run(root, "rev-parse", "HEAD")
    branch = git_run(root, "symbolic-ref", "HEAD")

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert out[-4].startswith(f"Spec Kit {FAKE_VERSION} initialized: {len(ALL_CREATED)} created, 0 skipped.")
    assert out[-3].startswith("Git: ")
    assert out[-2:] == NEXT_LINES
    assert git_run(root, "rev-parse", "HEAD") == head
    assert git_run(root, "symbolic-ref", "HEAD") == branch
    assert commit_count(root) == 1
    assert (root / "README.md").read_bytes() == b"hello\n"


def test_init_from_a_subdirectory_uses_the_git_top_level(runner, make_project):
    root = make_project(git=True)
    sub = root / "src"
    sub.mkdir()

    code, _, _ = runner.run(sub, "init")

    assert code == 0
    assert (root / RECORD).exists()
    assert list(sub.iterdir()) == []


# ======================================================= US1: no overwrite


def test_existing_files_are_skipped_and_left_untouched(runner, make_project):
    root = make_project(git=False)
    mine = [".specify/templates/plan-template.md", ".claude/skills/speckit-plan/SKILL.md"]
    write_tree(root, {p: "MINE" for p in mine})
    before = {p: (root / p).stat().st_mtime_ns for p in mine}

    code, out, _ = runner.run(root, "init")

    assert code == 0
    for p in mine:
        assert (root / p).read_bytes() == b"MINE"
        assert (root / p).stat().st_mtime_ns == before[p]
    assert of(out, "skipped") == [line("skipped", f"{p} (already exists, left untouched)") for p in sorted(mine)]
    created = [p for p in ALL_CREATED if p not in mine]
    assert of(out, "created") == [line("created", p) for p in created]
    assert entry_paths(root) == created
    assert out[-4] == f"Spec Kit {FAKE_VERSION} initialized: {len(created)} created, 2 skipped."
    for p in created:
        assert (root / p).exists()


def test_everything_already_present_without_a_record_is_all_skipped(runner, make_project):
    root = make_project(git=False)
    write_tree(root, {p: "THEIRS\n" for p in OFFICIAL})

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert of(out, "skipped") == [line("skipped", f"{p} (already exists, left untouched)") for p in OFFICIAL]
    assert of(out, "created") == [line("created", GITATTRIBUTES)]
    assert entry_paths(root) == [GITATTRIBUTES]
    assert out[-4] == f"Spec Kit {FAKE_VERSION} initialized: 1 created, {len(OFFICIAL)} skipped."
    for p in OFFICIAL:
        assert (root / p).read_bytes() == b"THEIRS\n"


# ========================================================= US1: idempotent


@pytest.mark.parametrize("git", [True, False])
def test_second_run_changes_nothing_and_does_not_go_online(runner, make_project, git):
    root = make_project(git=git)
    runner.run(root, "init")
    before = snap(root, with_mtime=True)
    before_status = status(root) if git else None
    before_index = index(root) if git else None
    runner.version_calls = 0
    runner.official_versions.clear()

    code, out, err = runner.run(root, "init")

    assert code == 0
    assert out == [f"Spec Kit {FAKE_VERSION} is already initialized. Nothing changed."]
    assert runner.version_calls == 0 and runner.official_versions == []
    assert snap(root, with_mtime=True) == before
    if git:
        assert status(root) == before_status
        assert index(root) == before_index


# ============================================== US1: repair and bad records


def test_missing_file_is_restored_with_the_recorded_version(runner, make_project):
    root = make_project(git=False)
    runner.run(root, "init")
    gone = ".specify/templates/plan-template.md"
    (root / gone).unlink()
    before = snap(root, with_mtime=True)
    runner.latest = "99.0.0"
    runner.version_calls = 0
    runner.official_versions.clear()

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert runner.version_calls == 0
    assert runner.official_versions == [FAKE_VERSION]
    assert of(out, "created") == [line("created", gone)]
    assert of(out, "skipped") == []
    assert out[-4] == f"Spec Kit {FAKE_VERSION} initialized: 1 created, 0 skipped."
    after = snap(root, with_mtime=True)
    assert (root / gone).read_bytes() == fake_official_files()[gone].encode()
    for key, value in before.items():
        if key != RECORD:
            assert after[key] == value, key
    record = read_record(root)
    assert record["status"] == "complete" and record["speckit_version"] == FAKE_VERSION
    assert [e["path"] for e in record["entries"]] == ALL_CREATED


def test_failure_while_copying_leaves_an_applying_record_and_the_next_run_finishes(
    runner, sdd_init, make_project, monkeypatch
):
    root = make_project(git=False)
    real_copy = sdd_init.copy_new_file
    calls = {"n": 0}

    def failing_copy(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full")
        real_copy(src, dst)

    monkeypatch.setattr(sdd_init, "copy_new_file", failing_copy)

    code, out, err = runner.run(root, "init")

    assert code == 1
    assert "disk full" in err and "/sdd-init" in err
    assert read_record(root)["status"] == "applying"
    assert not runner.dests[0].exists()
    existing = snap(root, with_mtime=True)
    assert len([k for k in existing if not k.endswith("/")]) < len(ALL_CREATED) + 1

    monkeypatch.setattr(sdd_init, "copy_new_file", real_copy)
    runner.latest = "99.0.0"
    runner.version_calls = 0
    runner.official_versions.clear()

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert runner.version_calls == 0 and runner.official_versions == [FAKE_VERSION]
    record = read_record(root)
    assert record["status"] == "complete"
    assert [e["path"] for e in record["entries"]] == ALL_CREATED
    after = snap(root, with_mtime=True)
    for key, value in existing.items():
        if key != RECORD:
            assert after[key] == value, key
    for rel, content in fake_official_files().items():
        assert (root / rel).read_bytes() == content.encode()
    created = [l.split()[1] for l in of(out, "created")]
    assert sorted(created + [k for k in existing if not k.endswith("/") and k != RECORD]) == ALL_CREATED

    code, out, _ = runner.run(root, "init")
    assert out == [f"Spec Kit {FAKE_VERSION} is already initialized. Nothing changed."]


def test_applying_record_with_all_files_present_becomes_complete(runner, make_project):
    root = make_project(git=False)
    runner.run(root, "init")
    record = read_record(root)
    record["status"] = "applying"
    (root / RECORD).write_bytes((json.dumps(record, indent=2) + "\n").encode())
    runner.version_calls = 0
    runner.official_versions.clear()

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert runner.version_calls == 0 and runner.official_versions == [FAKE_VERSION]
    assert read_record(root)["status"] == "complete"
    assert out[-4] == f"Spec Kit {FAKE_VERSION} initialized: 0 created, 0 skipped."


@pytest.mark.parametrize("name", sorted({**UNREADABLE_RECORDS, **BAD_PATH_RECORDS}))
def test_init_stops_on_an_invalid_record(runner, make_project, name):
    root = make_project(git=False)
    write_raw_record(root, {**UNREADABLE_RECORDS, **BAD_PATH_RECORDS}[name])
    write_tree(root, {"specs/x.md": "keep\n"})
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root, "init")

    assert code == 1
    assert ".specify/sdd-init.json" in err
    assert snap(root, with_mtime=True) == before
    assert runner.version_calls == 0 and runner.official_versions == []


# ================================================ US1: failures write nothing


@pytest.mark.parametrize(
    "missing",
    [["uv"], ["git"], ["bash"], ["bash", "uv"], ["bash", "git", "uv"]],
)
def test_missing_tools_are_all_listed_and_nothing_is_written(runner, sdd_init, make_project, monkeypatch, missing):
    root = make_project(git=False)
    write_tree(root, {"keep.txt": "x"})
    before = snap(root, with_mtime=True)
    # Pinned to the non-Windows wording; the Windows wording is covered further down.
    monkeypatch.setattr(sdd_init, "is_windows", lambda: False)
    monkeypatch.setattr(sdd_init, "find_tool", lambda name: None if name in missing else f"/bin/{name}")

    code, out, err = runner.run(root, "init")

    assert code == 3
    assert out == [line("missing", name) for name in sorted(missing)] + [
        "Missing required tools. Nothing was created. Install them and run /sdd-init again."
    ]
    for name in missing:
        assert name in err
    assert "install" in err.lower()
    assert snap(root, with_mtime=True) == before
    assert runner.version_calls == 0 and runner.official_versions == []


def unavailable_line(reason: str) -> str:
    return (
        f"Could not get the latest stable Spec Kit release: {reason}. Nothing was created. "
        "Check the network connection and run /sdd-init again."
    )


def test_version_lookup_failure_exits_4_and_writes_nothing(runner, make_project):
    root = make_project(git=True)
    before = snap(root, with_mtime=True)
    runner.resolve_error = "pypi.org cannot be reached"

    code, out, err = runner.run(root, "init")

    assert code == 4
    assert out == [unavailable_line("pypi.org cannot be reached")]
    assert "pypi.org cannot be reached" in err and "/sdd-init" in err
    assert snap(root, with_mtime=True) == before == {}
    assert runner.version_calls == 1 and runner.official_versions == []
    assert status(root) == ""


def test_official_tool_failure_exits_4_and_writes_nothing(runner, make_project):
    root = make_project(git=False)
    runner.official_error = "the official tool exited with code 1"

    code, out, err = runner.run(root, "init")

    assert code == 4
    assert out == [unavailable_line("the official tool exited with code 1")]
    assert "exited with code 1" in err and "/sdd-init" in err
    assert snap(root) == {}
    assert runner.version_calls == 1 and runner.official_versions == [FAKE_VERSION]
    assert not runner.dests[0].exists()


def test_version_mismatch_in_the_output_exits_4_and_writes_nothing(runner, make_project):
    root = make_project(git=False)
    runner.produced_version = "0.0.1"

    code, out, err = runner.run(root, "init")

    assert code == 4
    assert len(out) == 1
    assert out[0].startswith("Could not get the latest stable Spec Kit release: ")
    assert out[0].endswith(". Nothing was created. Check the network connection and run /sdd-init again.")
    assert "0.0.1" in err and FAKE_VERSION in err
    assert snap(root) == {}
    assert runner.version_calls == 1 and runner.official_versions == [FAKE_VERSION]
    assert not runner.dests[0].exists()


def test_output_without_init_options_exits_4(runner, sdd_init, make_project):
    root = make_project(git=False)

    def official(version, dest):
        write_tree(Path(dest), {".specify/templates/a.md": "a\n"})

    runner.monkeypatch.chdir(root)
    code = sdd_init.main(["init"], resolve_version=runner.resolve, run_official=official)

    assert code == 4
    assert snap(root) == {}


# ================================================= US2: .specify/.gitattributes


def test_gitattributes_is_created_with_exactly_one_rule(runner, make_project):
    root = make_project(git=True)

    code, out, _ = runner.run(root, "init")

    assert (root / GITATTRIBUTES).read_bytes() == GITATTRIBUTES_BYTES
    assert line("created", GITATTRIBUTES) in out
    entry = {e["path"]: e for e in read_record(root)["entries"]}[GITATTRIBUTES]
    assert entry["origin"] == "sdd-init"
    assert entry["staged_executable"] is False
    assert f"{len(OFFICIAL) + 1} created" in out[-4]
    assert of(out, "warning") == []
    for sh in OFFICIAL_SH:
        assert git_run(root, "check-attr", "eol", "--", sh).strip().endswith(": eol: lf")


@pytest.mark.parametrize(
    "git, content, warns",
    [
        (True, "scripts/bash/*.sh text eol=lf\n", False),
        (True, "# my own rules\n*.sh text eol=lf\n", False),
        (True, "# my own rules\n", True),
        (True, "scripts/bash/*.sh text eol=crlf\n", True),
        (False, "scripts/bash/*.sh text eol=lf\n", True),
    ],
)
def test_existing_gitattributes_is_left_alone_and_checked(runner, make_project, git, content, warns):
    root = make_project(git=git)
    write_tree(root, {GITATTRIBUTES: content})

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert (root / GITATTRIBUTES).read_bytes() == content.encode()
    assert line("skipped", f"{GITATTRIBUTES} (already exists, left untouched)") in out
    assert GITATTRIBUTES not in entry_paths(root)
    assert of(out, "warning") == ([WARNING_LINE] if warns else [])
    assert out[-4] == f"Spec Kit {FAKE_VERSION} initialized: {len(OFFICIAL)} created, 1 skipped."
    assert read_record(root)["status"] == "complete"


# ================================================================ US2: index


@pytest.mark.parametrize("filemode", ["true", "false"])
def test_new_sh_files_are_staged_as_executable(runner, make_project, filemode):
    root = make_project(git=True)
    git_run(root, "config", "core.fileMode", filemode)

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert of(out, "staged") == [
        line("staged", f"{p} (executable bit recorded in the git index)") for p in OFFICIAL_SH
    ]
    assert index(root) == {p: "100755" for p in OFFICIAL_SH}
    flags = {e["path"]: e["staged_executable"] for e in read_record(root)["entries"]}
    assert {p for p, v in flags.items() if v} == set(OFFICIAL_SH)
    assert commit_count(root) == 0
    assert out[-3] == (
        f"Git: {len(OFFICIAL_SH)} files were added to the index and nothing was committed. "
        f"{len(ALL_CREATED)} paths are uncommitted."
    )
    # Output order: created, staged, summary.
    kinds = [l.split(" ", 1)[0] for l in out[:-4]]
    assert kinds == ["created"] * len(ALL_CREATED) + ["staged"] * len(OFFICIAL_SH)


def test_skipped_sh_files_are_not_staged(runner, make_project):
    root = make_project(git=True)
    mine = OFFICIAL_SH[0]
    write_tree(root, {mine: "#!/bin/sh\necho mine\n"})

    code, out, _ = runner.run(root, "init")

    assert index(root) == {p: "100755" for p in OFFICIAL_SH[1:]}
    assert of(out, "staged") == [
        line("staged", f"{p} (executable bit recorded in the git index)") for p in OFFICIAL_SH[1:]
    ]
    assert out[-3] == (
        f"Git: {len(OFFICIAL_SH) - 1} files were added to the index and nothing was committed. "
        f"{len(ALL_CREATED) - 1} paths are uncommitted."
    )


def test_repair_of_a_committed_project_stages_nothing_and_counts_one_uncommitted_path(runner, make_project):
    root = make_project(git=True)
    runner.run(root, "init")
    commit_all(root, "spec kit")
    gone = ".specify/templates/plan-template.md"
    git_run(root, "rm", "--quiet", gone)
    git_run(root, "commit", "--quiet", "-m", "drop a template")
    commits = commit_count(root)

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert of(out, "created") == [line("created", gone)]
    assert of(out, "staged") == []
    assert out[-3] == "Git: nothing was added to the index. 1 paths are uncommitted."
    assert commit_count(root) == commits
    assert status(root).splitlines() == [f"?? {gone}"]


def test_outside_git_nothing_is_staged(runner, make_project):
    root = make_project(git=False)

    code, out, _ = runner.run(root, "init")

    assert of(out, "staged") == []
    assert out[-3] == GIT_NOT_A_REPO
    assert all(e["staged_executable"] is False for e in read_record(root)["entries"])


# ======================================================= US2: platform parity


def test_crlf_conversion_is_not_a_change(runner, make_project):
    root = make_project(git=False)
    runner.run(root, "init")
    for rel in ALL_CREATED:
        path = root / rel
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    before = snap(root, with_mtime=True)
    runner.version_calls = 0
    runner.official_versions.clear()

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert out == [f"Spec Kit {FAKE_VERSION} is already initialized. Nothing changed."]
    assert snap(root, with_mtime=True) == before
    assert runner.version_calls == 0 and runner.official_versions == []


@pytest.mark.parametrize("git", [True, False])
def test_output_and_record_do_not_depend_on_the_directory(runner, make_project, git):
    first = make_project(git=git, name="one")
    second = make_project(git=git, name="a-very-different-name")
    write_tree(second, {"unrelated.txt": "x"})

    code_a, out_a, _ = runner.run(first, "init")
    code_b, out_b, _ = runner.run(second, "init")

    assert code_a == code_b == 0
    assert out_a == out_b
    assert (first / RECORD).read_bytes() == (second / RECORD).read_bytes()
    assert "\\" not in "\n".join(out_a)
    assert b"\\" not in (first / RECORD).read_bytes()
    assert b"\r" not in (first / RECORD).read_bytes()

    code_a, rm_a, _ = runner.run(first, "remove")
    code_b, rm_b, _ = runner.run(second, "remove")
    assert rm_a == rm_b and "\\" not in "\n".join(rm_a)


# ============================================================== US3: remove


def test_remove_right_after_init_restores_the_project(runner, make_project):
    root = make_project(git=True)
    write_tree(root, {"README.md": "hello\n"})
    commit_all(root, "first")
    before = snap(root, with_mtime=True)
    before_status = status(root)
    before_index = git_run(root, "ls-files", "-s")
    runner.run(root, "init")

    code, out, _ = runner.run(root, "remove")

    assert code == 0
    assert of(out, "deleted") == [line("deleted", p) for p in ALL_CREATED]
    assert of(out, "unstaged") == [line("unstaged", p) for p in OFFICIAL_SH]
    assert of(out, "kept") == []
    assert out[-1] == f"Spec Kit removed: {len(ALL_CREATED)} deleted, 0 kept because they were modified."
    assert len(out) == len(ALL_CREATED) + len(OFFICIAL_SH) + 1
    assert snap(root, with_mtime=True) == before
    assert not (root / ".specify").exists() and not (root / ".claude").exists()
    assert status(root) == before_status
    assert git_run(root, "ls-files", "-s") == before_index
    assert commit_count(root) == 1


def test_remove_right_after_init_outside_git(runner, make_project):
    root = make_project(git=False)
    write_tree(root, {"README.md": "hello\n", ".claude/settings.json": "{}\n"})
    before = snap(root, with_mtime=True)
    runner.run(root, "init")

    code, out, _ = runner.run(root, "remove")

    assert code == 0
    assert of(out, "unstaged") == []
    assert of(out, "deleted") == [line("deleted", p) for p in ALL_CREATED]
    assert snap(root, with_mtime=True) == before
    assert not (root / ".git").exists()


def test_remove_keeps_modified_files_and_everything_it_did_not_create(runner, make_project):
    root = make_project(git=False)
    skipped = ".specify/templates/plan-template.md"
    write_tree(root, {skipped: "MINE"})
    runner.run(root, "init")
    constitution = root / ".specify/memory/constitution.md"
    constitution.write_bytes(constitution.read_bytes() + b"\n## My principle\n")
    kept_bytes = constitution.read_bytes()
    crlf = root / ".claude/skills/speckit-plan/SKILL.md"
    crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))
    gone = ".claude/skills/speckit-specify/SKILL.md"
    (root / gone).unlink()
    write_tree(root, {"specs/001-demo/spec.md": "my spec\n", ".specify/feature.json": "{}\n"})

    code, out, err = runner.run(root, "remove")

    assert code == 0
    assert of(out, "kept") == [line("kept", ".specify/memory/constitution.md (modified since init)")]
    assert constitution.read_bytes() == kept_bytes
    deleted = [p for p in ALL_CREATED if p not in (skipped, gone, ".specify/memory/constitution.md")]
    assert of(out, "deleted") == [line("deleted", p) for p in deleted]
    assert gone not in "\n".join(out) and err == ""
    assert out[-1] == f"Spec Kit removed: {len(deleted)} deleted, 1 kept because they were modified."
    assert not crlf.exists()
    assert (root / skipped).read_bytes() == b"MINE"
    assert (root / "specs/001-demo/spec.md").read_bytes() == b"my spec\n"
    assert (root / ".specify/feature.json").read_bytes() == b"{}\n"
    assert not (root / RECORD).exists()
    assert set(snap(root)) == {
        ".specify/",
        ".specify/feature.json",
        ".specify/memory/",
        ".specify/memory/constitution.md",
        ".specify/templates/",
        ".specify/templates/plan-template.md",
        "specs/",
        "specs/001-demo/",
        "specs/001-demo/spec.md",
    }


def test_remove_after_commit_leaves_the_index_alone(runner, make_project):
    root = make_project(git=True)
    runner.run(root, "init")
    commit_all(root, "spec kit")
    before_index = git_run(root, "ls-files", "-s")

    code, out, _ = runner.run(root, "remove")

    assert code == 0
    assert of(out, "unstaged") == []
    assert of(out, "deleted") == [line("deleted", p) for p in ALL_CREATED]
    assert git_run(root, "ls-files", "-s") == before_index
    rows = status(root).splitlines()
    assert sorted(rows) == sorted(f" D {p}" for p in ALL_CREATED + [RECORD])
    assert commit_count(root) == 1


def test_remove_does_not_remove_directories_it_did_not_create(runner, make_project):
    root = make_project(git=False)
    (root / ".claude" / "skills").mkdir(parents=True)

    runner.run(root, "init")
    runner.run(root, "remove")

    assert set(snap(root)) == {".claude/", ".claude/skills/"}


def test_remove_without_a_record_removes_nothing(runner, make_project):
    root = make_project(git=False)
    write_fake_official_output(root)
    before = snap(root, with_mtime=True)

    code, out, _ = runner.run(root, "remove")

    assert code == 0
    assert out == [NOTHING_TO_REMOVE]
    assert snap(root, with_mtime=True) == before


def test_remove_in_an_empty_directory(runner, make_project):
    root = make_project(git=False)

    code, out, _ = runner.run(root, "remove")

    assert code == 0 and out == [NOTHING_TO_REMOVE] and snap(root) == {}


@pytest.mark.parametrize("name", sorted(UNREADABLE_RECORDS))
def test_remove_with_an_unreadable_record_removes_nothing_and_exits_0(runner, make_project, name):
    root = make_project(git=False)
    write_fake_official_output(root)
    write_raw_record(root, UNREADABLE_RECORDS[name])
    before = snap(root, with_mtime=True)

    code, out, _ = runner.run(root, "remove")

    assert code == 0
    assert out == [NOTHING_REMOVED]
    assert snap(root, with_mtime=True) == before


@pytest.mark.parametrize("name", sorted(BAD_PATH_RECORDS))
def test_remove_refuses_records_with_paths_outside_spec_kit(runner, sdd_init, make_project, name):
    root = make_project(git=False)
    write_fake_official_output(root)
    write_tree(root, {"specs/x.md": "keep\n"})
    write_tree(root.parent, {"x": "keep\n"})
    data = json.loads(json.dumps(BAD_PATH_RECORDS[name]))
    # Give every entry the hash of the file it points at, so only the path rule protects it.
    for entry in data["entries"]:
        target = root / entry["path"]
        if not os.path.isabs(entry["path"]) and target.is_file():
            entry["sha256"] = sdd_init.content_hash(target.read_bytes())
    write_raw_record(root, data)
    before = snap(root, with_mtime=True)

    code, out, err = runner.run(root, "remove")

    assert code == 1
    assert out == [NOTHING_REMOVED]
    assert ".specify/sdd-init.json" in err
    assert snap(root, with_mtime=True) == before
    assert (root.parent / "x").read_bytes() == b"keep\n"


# ============================================ Windows: only Git Bash counts
#
# Simulated on any platform: is_windows() is forced to True, PATH points at
# made-up installations under tmp_path, and ask_git() answers from a table
# instead of running the made-up git. No bash.exe is ever executed.

MISSING_SUMMARY = "Missing required tools. Nothing was created. Install them and run /sdd-init again."
MISSING_GIT_BASH = line("missing", "bash (Git Bash, included with Git for Windows)")
GFW_VERSION = "git version 2.47.1.windows.2"
PLAIN_VERSION = "git version 2.47.1"


def tool_file(directory: Path, name: str) -> Path:
    """Create something shutil.which() accepts as the command `name` on this platform."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + ".exe" if os.name == "nt" else name)
    path.write_bytes(b"")
    path.chmod(0o755)
    return path


def bash_exe(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "bash.exe"
    path.write_bytes(b"")
    path.chmod(0o755)
    return path


class Machine:
    """A made-up Windows machine: directories on PATH and what each git answers."""

    def __init__(self, base: Path, module, monkeypatch):
        self.base = base
        self.module = module
        self.monkeypatch = monkeypatch
        self.path: list[Path] = []
        self.answers: dict[str, dict[str, str]] = {}
        self.asked: list[tuple[str, str]] = []
        monkeypatch.setattr(module, "is_windows", lambda: True)
        monkeypatch.setattr(module, "ask_git", self.ask)

    def ask(self, git_path, argument):
        self.asked.append((str(git_path), argument))
        return self.answers.get(os.path.normcase(str(git_path)), {}).get(argument)

    def apply(self) -> None:
        self.monkeypatch.setenv("PATH", os.pathsep.join(str(p) for p in self.path))

    def add_uv(self) -> None:
        tool_file(self.base / "uv-bin", "uv")
        self.path.append(self.base / "uv-bin")
        self.apply()

    def add_wsl_launcher(self) -> Path:
        """C:\\Windows\\System32\\bash.exe: on PATH, but not Git Bash."""
        launcher = bash_exe(self.base / "Windows" / "System32")
        self.path.append(launcher.parent)
        self.apply()
        return launcher

    def add_git_for_windows(self, where: str = "Program Files/Git", bash: str | None = "bin") -> Path:
        """A Git for Windows layout at any location; returns its root."""
        root = self.base / where
        exec_path = root / "mingw64" / "libexec" / "git-core"
        exec_path.mkdir(parents=True)
        if bash is not None:
            bash_exe(root / bash)
        git = tool_file(root / "cmd", "git")
        self.answers[os.path.normcase(str(git))] = {"--version": GFW_VERSION, "--exec-path": exec_path.as_posix()}
        self.path.append(git.parent)
        self.apply()
        return root

    def add_other_git(self, where: str = "msys64") -> Path:
        """A git that is not Git for Windows, with its own bash next to it."""
        root = self.base / where
        (root / "usr" / "lib" / "git-core").mkdir(parents=True)
        bash_exe(root / "usr" / "bin")
        git = tool_file(root / "usr" / "bin", "git")
        self.answers[os.path.normcase(str(git))] = {
            "--version": PLAIN_VERSION,
            "--exec-path": (root / "usr" / "lib" / "git-core").as_posix(),
        }
        self.path.append(git.parent)
        self.apply()
        return root


@pytest.fixture
def machine(sdd_init, tmp_path, monkeypatch):
    base = tmp_path / "machine"
    base.mkdir()
    return Machine(base, sdd_init, monkeypatch)  # PATH is replaced by the first add_*()


def same_file(found, expected: Path) -> bool:
    return found is not None and os.path.samefile(found, expected)


def test_windows_git_bash_alone_is_found(sdd_init, machine):
    root = machine.add_git_for_windows()

    assert same_file(sdd_init.find_tool("bash"), root / "bin" / "bash.exe")


def test_windows_wsl_launcher_ahead_on_path_does_not_hide_git_bash(sdd_init, machine):
    launcher = machine.add_wsl_launcher()
    root = machine.add_git_for_windows()

    found = sdd_init.find_tool("bash")

    assert same_file(found, root / "bin" / "bash.exe")
    assert not os.path.samefile(found, launcher)


def test_windows_wsl_launcher_behind_on_path_changes_nothing(sdd_init, machine):
    root = machine.add_git_for_windows()
    machine.add_wsl_launcher()

    assert same_file(sdd_init.find_tool("bash"), root / "bin" / "bash.exe")


@pytest.mark.parametrize("where", ["scoop/apps/git/current", "D/tools/PortableGit", "odd place/with spaces/G"])
def test_windows_git_bash_is_found_wherever_git_is_installed(sdd_init, machine, where):
    machine.add_wsl_launcher()
    root = machine.add_git_for_windows(where=where)

    assert same_file(sdd_init.find_tool("bash"), root / "bin" / "bash.exe")


def test_windows_git_bash_under_usr_bin_is_accepted(sdd_init, machine):
    root = machine.add_git_for_windows(bash="usr/bin")

    assert same_file(sdd_init.find_tool("bash"), root / "usr" / "bin" / "bash.exe")


def test_windows_a_later_git_for_windows_is_used_when_the_first_git_is_another_one(sdd_init, machine):
    machine.add_other_git()
    root = machine.add_git_for_windows()

    assert same_file(sdd_init.find_tool("bash"), root / "bin" / "bash.exe")


def test_windows_wsl_launcher_alone_is_not_bash(sdd_init, machine):
    machine.add_wsl_launcher()

    assert sdd_init.find_tool("bash") is None
    assert machine.asked == [], "there is no git to ask"


def test_windows_bash_of_a_git_that_is_not_git_for_windows_is_not_accepted(sdd_init, machine):
    machine.add_wsl_launcher()
    machine.add_other_git()

    assert sdd_init.find_tool("bash") is None
    assert [argument for _git, argument in machine.asked] == ["--version"]


def test_windows_git_for_windows_without_bash_is_not_accepted(sdd_init, machine):
    machine.add_wsl_launcher()
    machine.add_git_for_windows(bash=None)

    assert sdd_init.find_tool("bash") is None


def test_windows_git_that_does_not_answer_is_not_accepted(sdd_init, machine):
    root = machine.add_git_for_windows()
    machine.answers.clear()

    assert sdd_init.find_tool("bash") is None
    assert (root / "bin" / "bash.exe").is_file()


def test_windows_other_tools_are_still_looked_up_on_path(sdd_init, machine):
    machine.add_uv()

    assert sdd_init.find_tool("uv") is not None
    assert sdd_init.find_tool("git") is None


def test_ask_git_ignores_git_exec_path_from_the_environment(sdd_init, monkeypatch, tmp_path):
    import shutil

    real = shutil.which("git")
    expected = subprocess.run([real, "--exec-path"], capture_output=True, text=True, check=True).stdout.strip()
    monkeypatch.setenv("GIT_EXEC_PATH", str(tmp_path / "elsewhere"))

    assert sdd_init.ask_git(real, "--exec-path") == expected
    assert sdd_init.ask_git(real, "--version").startswith("git version ")
    assert sdd_init.ask_git(str(tmp_path / "no-such-git"), "--version") is None


def test_non_windows_bash_is_whatever_is_on_path(sdd_init, monkeypatch, tmp_path):
    monkeypatch.setattr(sdd_init, "is_windows", lambda: False)
    monkeypatch.setattr(sdd_init, "ask_git", lambda *a: pytest.fail("git must not be asked outside Windows"))
    here = tool_file(tmp_path / "bin", "bash")
    monkeypatch.setenv("PATH", str(here.parent))

    assert same_file(sdd_init.find_tool("bash"), here)

    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert sdd_init.find_tool("bash") is None


WINDOWS_WITHOUT_GIT_BASH = {
    "wsl launcher only, no git": (["wsl"], ["bash", "git"]),
    "wsl launcher and a git that is not Git for Windows": (["wsl", "other"], ["bash"]),
    "Git for Windows without bash, wsl launcher ahead": (["wsl", "gfw-no-bash"], ["bash"]),
    "neither": ([], ["bash", "git"]),
}


@pytest.mark.parametrize("name", sorted(WINDOWS_WITHOUT_GIT_BASH))
def test_windows_without_git_bash_exits_3_and_writes_nothing(runner, machine, make_project, name):
    parts, missing = WINDOWS_WITHOUT_GIT_BASH[name]
    root = make_project(git=False)
    write_tree(root, {"keep.txt": "x"})
    before = snap(root, with_mtime=True)
    machine.add_uv()
    for part in parts:
        if part == "wsl":
            machine.add_wsl_launcher()
        elif part == "other":
            machine.add_other_git()
        else:
            machine.add_git_for_windows(bash=None)

    code, out, err = runner.run(root, "init")

    assert code == 3
    expected = {"bash": MISSING_GIT_BASH, "git": line("missing", "git")}
    assert out == [expected[tool] for tool in missing] + [MISSING_SUMMARY]
    assert f"error: required tools are missing: {', '.join(missing)}" in err
    assert "Git for Windows" in err and "WSL" in err
    assert "install" in err.lower()
    assert snap(root, with_mtime=True) == before
    assert runner.version_calls == 0 and runner.official_versions == []


def test_windows_missing_uv_only_keeps_the_plain_wording(runner, machine, make_project):
    root = make_project(git=False)
    machine.add_wsl_launcher()
    machine.add_git_for_windows()

    code, out, err = runner.run(root, "init")

    assert code == 3
    assert out == [line("missing", "uv"), MISSING_SUMMARY]
    assert "WSL" not in err
    assert snap(root) == {}


def test_windows_with_git_bash_behind_the_wsl_launcher_initializes(runner, sdd_init, machine, make_project, monkeypatch):
    """Whole run: the real git and uv stay in use, only the questions to git are answered by the table."""
    import shutil

    root = make_project(git=True)
    real_path = os.environ["PATH"]
    install = machine.base / "Git"
    (install / "mingw64" / "libexec" / "git-core").mkdir(parents=True)
    bash_exe(install / "bin")
    launcher = machine.add_wsl_launcher()
    monkeypatch.setenv("PATH", os.pathsep.join([str(launcher.parent), real_path]))
    real_git = shutil.which("git")
    assert real_git, "the test machine needs git"
    machine.answers[os.path.normcase(real_git)] = {
        "--version": GFW_VERSION,
        "--exec-path": (install / "mingw64" / "libexec" / "git-core").as_posix(),
    }
    assert same_file(sdd_init.find_tool("bash"), install / "bin" / "bash.exe")

    code, out, _err = runner.run(root, "init")

    assert code == 0
    assert of(out, "missing") == []
    assert out[-4] == f"Spec Kit {FAKE_VERSION} initialized: {len(ALL_CREATED)} created, 0 skipped."


# ============================== convergence: staging .sh left unstaged earlier

ALREADY = f"Spec Kit {FAKE_VERSION} is already initialized. Nothing changed."
RESTAGED_ONLY = f"Spec Kit {FAKE_VERSION} is already initialized. Nothing was created."


def staged_line(path: str) -> str:
    return line("staged", f"{path} (executable bit recorded in the git index)")


def git_added_line(added: int, uncommitted: int) -> str:
    return f"Git: {added} files were added to the index and nothing was committed. {uncommitted} paths are uncommitted."


def flags(root: Path) -> dict[str, bool]:
    return {e["path"]: e["staged_executable"] for e in read_record(root)["entries"]}


def branch(root: Path) -> str:
    return git_run(root, "symbolic-ref", "HEAD").strip()


def like_windows(root: Path) -> None:
    """A repository that ignores file modes, with no executable bit on any .sh in the work tree."""
    git_run(root, "config", "core.fileMode", "false")
    for path in OFFICIAL_SH:
        if (root / path).exists():
            os.chmod(root / path, 0o644)


def fail_git_add(sdd_init, monkeypatch) -> None:
    """Make every `git add` of sdd-init fail, the way a locked index would."""
    real_git = sdd_init.git

    def git_without_add(cwd, *args):
        if args and args[0] == "add":
            return subprocess.CompletedProcess(["git", *args], 128, b"", b"fatal: Unable to create index.lock\n")
        return real_git(cwd, *args)

    monkeypatch.setattr(sdd_init, "git", git_without_add)


def init_with_failed_git_add(runner, sdd_init, root: Path, monkeypatch) -> None:
    """A first init whose files are all copied but whose `git add --chmod=+x` fails."""
    with monkeypatch.context() as patch:
        fail_git_add(sdd_init, patch)
        code, out, err = runner.run(root, "init")
    assert code == 0
    assert of(out, "staged") == []
    assert [l for l in err.splitlines() if l.startswith("note: ")] != []
    assert read_record(root)["status"] == "complete"
    runner.version_calls = 0
    runner.official_versions.clear()


def assert_nothing_changes_on_another_run(runner, root: Path) -> None:
    before = snap(root, with_mtime=True)
    before_index, before_status = index(root), status(root)
    runner.version_calls = 0
    runner.official_versions.clear()

    code, out, err = runner.run(root, "init")

    assert code == 0
    assert out == [ALREADY]
    assert err == ""
    assert runner.version_calls == 0 and runner.official_versions == []
    assert snap(root, with_mtime=True) == before
    assert index(root) == before_index and status(root) == before_status


@pytest.mark.parametrize("filemode", ["true", "false"])
def test_repair_after_a_failed_copy_stages_the_sh_copied_by_the_earlier_run(
    runner, sdd_init, make_project, monkeypatch, filemode
):
    root = make_project(git=True)
    git_run(root, "config", "core.fileMode", filemode)
    head = branch(root)
    real_copy = sdd_init.copy_new_file
    copied: list[str] = []
    second_sh = OFFICIAL_SH[1]

    def failing_copy(src, dst):
        if Path(dst).relative_to(root).as_posix() == second_sh:
            raise OSError("disk full")
        real_copy(src, dst)
        copied.append(Path(dst).relative_to(root).as_posix())

    monkeypatch.setattr(sdd_init, "copy_new_file", failing_copy)
    code, _, _ = runner.run(root, "init")
    assert code == 1
    assert read_record(root)["status"] == "applying"
    assert OFFICIAL_SH[0] in copied and second_sh not in copied
    assert index(root) == {}
    monkeypatch.setattr(sdd_init, "copy_new_file", real_copy)
    if filemode == "false":
        like_windows(root)

    code, out, err = runner.run(root, "init")

    assert code == 0 and err == ""
    assert of(out, "staged") == [staged_line(p) for p in OFFICIAL_SH]
    assert index(root) == {p: "100755" for p in OFFICIAL_SH}
    assert flags(root) == {p: p in OFFICIAL_SH for p in ALL_CREATED}
    created = [l.split()[1] for l in of(out, "created")]
    assert sorted(created + copied) == ALL_CREATED
    assert out[-4] == f"Spec Kit {FAKE_VERSION} initialized: {len(created)} created, 0 skipped."
    assert out[-3] == git_added_line(len(OFFICIAL_SH), len(ALL_CREATED))
    assert out[-2:] == NEXT_LINES
    assert commit_count(root) == 0 and branch(root) == head

    assert_nothing_changes_on_another_run(runner, root)

    # What the maintainer does next must keep the executable bit.
    git_run(root, "add", "-A")
    modes = index(root)
    assert {p: modes[p] for p in OFFICIAL_SH} == {p: "100755" for p in OFFICIAL_SH}


@pytest.mark.parametrize("filemode", ["true", "false"])
def test_complete_record_with_unstaged_sh_only_stages_them(runner, sdd_init, make_project, monkeypatch, filemode):
    root = make_project(git=True)
    git_run(root, "config", "core.fileMode", filemode)
    head = branch(root)
    init_with_failed_git_add(runner, sdd_init, root, monkeypatch)
    if filemode == "false":
        like_windows(root)
    assert index(root) == {}
    assert not any(flags(root).values())
    before = snap(root, with_mtime=True)
    runner.latest = "99.0.0"

    code, out, err = runner.run(root, "init")

    assert code == 0 and err == ""
    assert out == [staged_line(p) for p in OFFICIAL_SH] + [
        RESTAGED_ONLY,
        git_added_line(len(OFFICIAL_SH), len(ALL_CREATED)),
        *NEXT_LINES,
    ]
    assert runner.version_calls == 0 and runner.official_versions == []
    assert index(root) == {p: "100755" for p in OFFICIAL_SH}
    assert flags(root) == {p: p in OFFICIAL_SH for p in ALL_CREATED}
    after = snap(root, with_mtime=True)
    assert set(after) == set(before)
    assert {k: v for k, v in after.items() if k != RECORD} == {k: v for k, v in before.items() if k != RECORD}
    record = read_record(root)
    assert record["status"] == "complete" and record["speckit_version"] == FAKE_VERSION
    assert commit_count(root) == 0 and branch(root) == head

    assert_nothing_changes_on_another_run(runner, root)

    git_run(root, "add", "-A")
    modes = index(root)
    assert {p: modes[p] for p in OFFICIAL_SH} == {p: "100755" for p in OFFICIAL_SH}


def test_staging_that_fails_again_is_reported_and_retried_by_the_next_run(runner, sdd_init, make_project, monkeypatch):
    root = make_project(git=True)
    init_with_failed_git_add(runner, sdd_init, root, monkeypatch)
    before = snap(root, with_mtime=True)

    with monkeypatch.context() as patch:
        fail_git_add(sdd_init, patch)
        code, out, err = runner.run(root, "init")

    assert code == 0
    assert out == [
        RESTAGED_ONLY,
        f"Git: nothing was added to the index. {len(ALL_CREATED)} paths are uncommitted.",
        *NEXT_LINES,
    ]
    assert err.splitlines() == [
        f"note: {p} was not added to the git index: fatal: Unable to create index.lock" for p in OFFICIAL_SH
    ]
    assert snap(root, with_mtime=True) == before  # the record is not rewritten either
    assert index(root) == {}
    assert runner.version_calls == 0 and runner.official_versions == []

    code, out, _ = runner.run(root, "init")

    assert of(out, "staged") == [staged_line(p) for p in OFFICIAL_SH]
    assert index(root) == {p: "100755" for p in OFFICIAL_SH}


@pytest.mark.parametrize("where", ["index", "head"])
def test_sh_already_in_the_index_or_in_head_is_left_alone(runner, sdd_init, make_project, monkeypatch, where):
    root = make_project(git=True)
    git_run(root, "config", "core.fileMode", "false")
    init_with_failed_git_add(runner, sdd_init, root, monkeypatch)
    like_windows(root)
    git_run(root, "add", "-A")
    if where == "head":
        git_run(root, "commit", "--quiet", "-m", "spec kit")
    commits = commit_count(root)
    assert {index(root)[p] for p in OFFICIAL_SH} == {"100644"}

    assert_nothing_changes_on_another_run(runner, root)

    assert {index(root)[p] for p in OFFICIAL_SH} == {"100644"}
    assert not any(flags(root).values())
    assert commit_count(root) == commits


def test_skipped_sh_is_not_staged_later_either(runner, sdd_init, make_project, monkeypatch):
    root = make_project(git=True)
    mine = OFFICIAL_SH[0]
    write_tree(root, {mine: "#!/bin/sh\necho mine\n"})
    init_with_failed_git_add(runner, sdd_init, root, monkeypatch)
    assert mine not in entry_paths(root)

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert of(out, "staged") == [staged_line(p) for p in OFFICIAL_SH[1:]]
    assert out[-4] == RESTAGED_ONLY
    assert out[-3] == git_added_line(len(OFFICIAL_SH) - 1, len(ALL_CREATED) - 1)
    assert index(root) == {p: "100755" for p in OFFICIAL_SH[1:]}
    assert (root / mine).read_bytes() == b"#!/bin/sh\necho mine\n"


def test_only_sh_entries_that_came_from_spec_kit_are_staged_later(runner, sdd_init, make_project, monkeypatch):
    root = make_project(git=True)
    init_with_failed_git_add(runner, sdd_init, root, monkeypatch)
    own = OFFICIAL_SH[0]
    record = read_record(root)
    for entry in record["entries"]:
        if entry["path"] == own:
            entry["origin"] = "sdd-init"
    (root / RECORD).write_bytes((json.dumps(record, indent=2) + "\n").encode())

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert of(out, "staged") == [staged_line(p) for p in OFFICIAL_SH[1:]]
    assert index(root) == {p: "100755" for p in OFFICIAL_SH[1:]}  # no other file, .sh or not, was added
    assert flags(root) == {p: p in OFFICIAL_SH[1:] for p in ALL_CREATED}


def test_repair_outside_git_after_a_failed_copy_stages_nothing(runner, sdd_init, make_project, monkeypatch):
    root = make_project(git=False)
    real_copy = sdd_init.copy_new_file

    def failing_copy(src, dst):
        if Path(dst).relative_to(root).as_posix() == OFFICIAL_SH[1]:
            raise OSError("disk full")
        real_copy(src, dst)

    monkeypatch.setattr(sdd_init, "copy_new_file", failing_copy)
    assert runner.run(root, "init")[0] == 1
    monkeypatch.setattr(sdd_init, "copy_new_file", real_copy)

    code, out, _ = runner.run(root, "init")

    assert code == 0
    assert of(out, "staged") == []
    assert out[-3] == GIT_NOT_A_REPO
    assert not any(flags(root).values())
    assert not (root / ".git").exists()


def test_project_that_became_a_repository_after_init_gets_its_sh_staged(runner, make_project):
    root = make_project(git=False)
    runner.run(root, "init")
    assert runner.run(root, "init")[1] == [ALREADY]
    git_run(root, "init", "--quiet")
    like_windows(root)
    before = snap(root, with_mtime=True)
    runner.version_calls = 0
    runner.official_versions.clear()

    code, out, err = runner.run(root, "init")

    assert code == 0 and err == ""
    assert out == [staged_line(p) for p in OFFICIAL_SH] + [
        RESTAGED_ONLY,
        git_added_line(len(OFFICIAL_SH), len(ALL_CREATED)),
        *NEXT_LINES,
    ]
    assert runner.version_calls == 0 and runner.official_versions == []
    assert index(root) == {p: "100755" for p in OFFICIAL_SH}
    after = snap(root, with_mtime=True)
    assert {k: v for k, v in after.items() if k != RECORD} == {k: v for k, v in before.items() if k != RECORD}
    assert commit_count(root) == 0

    assert_nothing_changes_on_another_run(runner, root)


def test_sh_taken_out_of_the_index_is_staged_again_only_when_init_never_staged_it(
    runner, sdd_init, make_project, monkeypatch
):
    # staged_executable is true: init staged it once, the maintainer removed it, init leaves it alone.
    root = make_project(git=True)
    runner.run(root, "init")
    git_run(root, "rm", "--cached", "--quiet", "--", *OFFICIAL_SH)
    assert_nothing_changes_on_another_run(runner, root)
    assert index(root) == {}

    # staged_executable is false: the maintainer staged and unstaged it, init stages it.
    other = make_project(git=True)
    init_with_failed_git_add(runner, sdd_init, other, monkeypatch)
    git_run(other, "add", "--", *OFFICIAL_SH)
    git_run(other, "rm", "--cached", "--quiet", "--", *OFFICIAL_SH)

    code, out, _ = runner.run(other, "init")

    assert code == 0
    assert of(out, "staged") == [staged_line(p) for p in OFFICIAL_SH]
    assert index(other) == {p: "100755" for p in OFFICIAL_SH}


def test_remove_unstages_what_a_later_init_staged(runner, sdd_init, make_project, monkeypatch):
    root = make_project(git=True)
    init_with_failed_git_add(runner, sdd_init, root, monkeypatch)
    runner.run(root, "init")
    assert index(root) == {p: "100755" for p in OFFICIAL_SH}

    code, out, _ = runner.run(root, "remove")

    assert code == 0
    assert of(out, "unstaged") == [line("unstaged", p) for p in OFFICIAL_SH]
    assert index(root) == {} and status(root) == ""
