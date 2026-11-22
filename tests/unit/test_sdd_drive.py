"""Unit tests for home/skills/sdd-drive/scripts/sdd_drive.py.

The contract is specs/008-sdd-drive/contracts/cli.md and data-model.md. Every test builds its own fake project under
tmp_path; HOME points at a temporary folder, git ignores the global and system settings, and the child session is
always the fake claude (tests/unit/fixtures/sdd_drive/fake_claude.py) named by SDD_DRIVE_CLAUDE. The real claude is
never started and the real ~/.claude is never read.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from conftest import REPO_ROOT, git_run, tree_snapshot, write_tree

SCRIPT = REPO_ROOT / "home" / "skills" / "sdd-drive" / "scripts" / "sdd_drive.py"
FAKE_CLAUDE = REPO_ROOT / "tests" / "unit" / "fixtures" / "sdd_drive" / "fake_claude.py"
OWN_GITIGNORE = b"# Created by sdd-drive. Local run records; never committed.\n*\n"
SECRET_TEXT = "(not shown: looks like a secret)"
SECRET_VALUE = "ghp_" + "a" * 30
AUTO_REASON = "Automatic resume after the usage limit reset."
PY = sys.executable
PASS_CMD = f'"{PY}" -c "import sys; sys.exit(0)"'
FAIL_CMD = f'"{PY}" -c "import sys; print(\'boom\'); sys.exit(3)"'
TIMING = {"poll_seconds": 0.05, "margin_seconds": 0.2, "watch_seconds": 30}


# ------------------------------------------------------------------ fixtures


@pytest.fixture(scope="session")
def drive_module():
    spec = importlib.util.spec_from_file_location("sdd_drive_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def drive_env(tmp_path, monkeypatch):
    home = tmp_path / "fake-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    empty = home / "empty-gitconfig"
    empty.write_bytes(b"")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "FAKE_CLAUDE_SCENARIOS"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("SDD_DRIVE_CLAUDE", json.dumps([PY, str(FAKE_CLAUDE)]))
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(TIMING))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "fake-claude-log.jsonl"))
    monkeypatch.setenv("FAKE_CLAUDE_COUNTER", str(tmp_path / "fake-claude-counter"))
    return tmp_path


class Result:
    def __init__(self, code: int, out: bytes, err: bytes):
        self.code = code
        self.out = out
        self.err = err

    def describe(self) -> str:
        """The whole outcome, for assertion messages: when CI fails, the log shows why."""
        return (f"exit code {self.code}\nstdout:\n{self.out.decode('utf-8', 'replace')}\n"
                f"stderr:\n{self.err.decode('utf-8', 'replace')}")

    @property
    def json(self) -> dict:
        try:
            return json.loads(self.out.decode("utf-8"))
        except ValueError:
            raise AssertionError("output is not JSON\n" + self.describe()) from None

    @property
    def watched(self) -> dict:
        """The output of run or watch; fails with the whole output when it has no attempts (an error, for example)."""
        data = self.json
        assert self.code == 0 and "attempts" in data and "status" in data, self.describe()
        return data

    @property
    def text(self) -> str:
        return self.out.decode("utf-8")


def drive(module, root: Path, *argv: str) -> Result:
    """Call main the way `uv run sdd_drive.py <argv>` would, in root."""
    out, err = io.BytesIO(), io.BytesIO()
    code = module.main(list(argv), root=root, stdout=out, stderr=err)
    return Result(code, out.getvalue(), err.getvalue())


def drive_real(root: Path, *argv: str, script: Path = SCRIPT, **kwargs) -> subprocess.CompletedProcess:
    """Run the real script through uv in root."""
    return subprocess.run(["uv", "run", "--quiet", str(script), *argv], cwd=root, capture_output=True,
                          stdin=subprocess.DEVNULL, **kwargs)


def scenarios(monkeypatch, *items: dict) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIOS", json.dumps(list(items)))


def calls(tmp_path: Path) -> list[dict]:
    log = tmp_path / "fake-claude-log.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


SPECKIT_SKILLS = ("speckit-plan", "speckit-tasks", "speckit-implement", "speckit-converge")


GIT_SETTINGS = "[user]\n\tname = test\n\temail = test@example.invalid\n[core]\n\tautocrlf = false\n"


def make_project(tmp_path: Path, name: str = "proj", git: bool = True, skills=SPECKIT_SKILLS, specs: dict | None = None,
                 commit: bool = True) -> Path:
    """A fake project: Spec Kit's templates and scripts copied from this repo, minimal speckit-* skills."""
    root = tmp_path / name
    root.mkdir()
    shutil.copytree(REPO_ROOT / ".specify" / "templates", root / ".specify" / "templates")
    shutil.copytree(REPO_ROOT / ".specify" / "scripts", root / ".specify" / "scripts")
    files = {".specify/memory/constitution.md": "# Constitution\n\nTests run with pytest.\n"}
    for skill in skills:
        files[f".claude/skills/{skill}/SKILL.md"] = f"---\nname: {skill}\n---\n{skill}\n"
    write_tree(root, files)
    for spec_name, options in (specs or {}).items():
        add_spec(root, spec_name, **options)
    if git:
        git_run(root, "init", "--quiet")
        # The same three settings as `git config user.name test` and so on, without three more processes
        # (each process start costs much more on Windows; test_project_git_settings checks the result).
        with open(root / ".git" / "config", "a", encoding="utf-8", newline="\n") as config:
            config.write(GIT_SETTINGS)
        if commit:
            commit_all(root, "initial")
    return root


def test_project_git_settings(tmp_path):
    root = make_project(tmp_path)
    assert git_run(root, "config", "--local", "--get", "user.name").strip() == "test"
    assert git_run(root, "config", "--local", "--get", "user.email").strip() == "test@example.invalid"
    assert git_run(root, "config", "--local", "--get", "core.autocrlf").strip() == "false"
    assert git_run(root, "log", "--format=%an <%ae>").strip() == "test <test@example.invalid>"


def commit_all(root: Path, message: str = "commit") -> None:
    git_run(root, "add", "-A")
    git_run(root, "commit", "--quiet", "--allow-empty", "-m", message)


def spec_text(name: str, requirements: int = 3, stories: int = 2) -> str:
    lines = [f"# Feature Specification: {name}", ""]
    lines += [f"### User Story {i} - story (Priority: P1)" for i in range(1, stories + 1)]
    lines += [f"- **FR-{i:03d}**: requirement {i}" for i in range(1, requirements + 1)]
    return "\n".join(lines) + "\n"


def plan_text(name: str, command: str | None = PASS_CMD) -> str:
    testing = f"**Testing**: `{command}`" if command is not None else "**Testing**: pytest"
    return f"# Implementation Plan: {name}\n\n**Language/Version**: Python 3.11\n\n{testing}\n\nBody.\n"


def tasks_text(name: str, total: int, checked: int = 0) -> str:
    lines = [f"# Tasks: {name}", "", "## Phase 1: Setup", ""]
    for i in range(1, total + 1):
        mark = "x" if i <= checked else " "
        lines.append(f"- [{mark}] T{i:03d} Do step {i}")
    return "\n".join(lines) + "\n"


def add_spec(root: Path, name: str, plan: bool | str = False, tasks: tuple[int, int] | str | None = None,
             command: str | None = PASS_CMD) -> None:
    files = {f"specs/{name}/spec.md": spec_text(name)}
    if plan is True:
        files[f"specs/{name}/plan.md"] = plan_text(name, command)
    elif isinstance(plan, str):
        files[f"specs/{name}/plan.md"] = plan
    if isinstance(tasks, tuple):
        files[f"specs/{name}/tasks.md"] = tasks_text(name, *tasks)
    elif isinstance(tasks, str):
        files[f"specs/{name}/tasks.md"] = tasks
    write_tree(root, files)


def bare_remote(tmp_path: Path, root: Path) -> Path:
    remote = tmp_path / "remote.git"
    git_run(tmp_path, "init", "--quiet", "--bare", str(remote))
    git_run(root, "remote", "add", "origin", str(remote))
    git_run(root, "push", "--quiet", "origin", "HEAD")
    git_run(root, "fetch", "--quiet", "origin")
    return remote


def state_file(root: Path) -> Path:
    return root / ".specify" / "sdd-drive" / "state.json"


def read_state(root: Path) -> dict:
    """state.json; on Windows a read may meet the driver replacing the file, so PermissionError is retried."""
    deadline = time.monotonic() + 5
    while True:
        try:
            data = state_file(root).read_bytes()
            break
        except PermissionError:
            if os.name != "nt" or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)
    return json.loads(data.decode("utf-8"))


def write_state(root: Path, state: dict) -> None:
    folder = root / ".specify" / "sdd-drive"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".gitignore").write_bytes(OWN_GITIGNORE)
    state_file(root).write_bytes((json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def blank_state(baseline=(), **changes) -> dict:
    state = {"tool": "sdd-drive", "schema": 1, "attempts": [], "baseline": list(baseline), "baseline_reset": False,
             "launch": None, "driver": None, "tests": []}
    state.update(changes)
    return state


UUID1 = "11111111-1111-4111-8111-111111111111"
UUID2 = "22222222-2222-4222-8222-222222222222"
T0 = "2026-11-21T10:00:00Z"
T1 = "2026-11-21T10:05:00Z"


def attempt(id: int = 1, spec: str = "001-alpha", phase: str = "plan", outcome: str | None = "succeeded",
            **changes) -> dict:
    record = {
        "id": id, "spec": spec, "phase": phase, "session_id": UUID1, "resume": False, "model": "opus",
        "model_used": ["claude-opus-test"], "reason": "Design work.", "started_at": T0,
        "ended_at": None if outcome is None else T1, "outcome": outcome, "detail": None, "report": None,
        "worktree": None, "task_ids": None, "convergence": None, "tasks_hash": None, "appended": None, "auto": False,
        "limit": None, "auto_resume": None, "permission_denials": [],
    }
    record.update(changes)
    return record


def test_record(spec: str, tasks_hash: str, exit_code: int = 0, head: str | None = None, command: str = "pytest") -> dict:
    return {"spec": spec, "tasks_hash": tasks_hash, "command": command, "exit_code": exit_code, "head": head, "at": T0}


test_record.__test__ = False  # not a test function


def head_of(root: Path) -> str:
    return git_run(root, "rev-parse", "HEAD").strip()


def hash_of(module, root: Path, spec: str) -> str:
    module.load_grill()
    return module.tasks_hash(root, spec)


LOCK_HOLDER = r"""
import os, sys, time
path = sys.argv[1]
os.makedirs(os.path.dirname(path), exist_ok=True)
handle = open(path, "a+b")
if os.name == "nt":
    import msvcrt
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
print("locked", flush=True)
sys.stdin.readline()
"""


@contextlib.contextmanager
def hold_lock(root: Path):
    """Another process holds .specify/sdd-drive/lock until the block ends.

    Inside the block every platform behaves like Windows: reading the lock file fails (windows_lock_reads).
    """
    folder = root / ".specify" / "sdd-drive"
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".gitignore").exists():
        (folder / ".gitignore").write_bytes(OWN_GITIGNORE)
    holder = subprocess.Popen([PY, "-c", LOCK_HOLDER, str(folder / "lock")], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE)
    try:
        assert holder.stdout.readline().strip() == b"locked"
        with pytest.MonkeyPatch.context() as patch, windows_lock_reads(patch, root):
            yield holder
    finally:
        if holder.poll() is None:
            holder.stdin.close()
            holder.wait(timeout=30)


LOCK_REL = ".specify/sdd-drive/lock"


def snapshot_without_lock(root: Path) -> dict:
    """tree_snapshot that never opens the lock file: while it is locked, Windows refuses to read its bytes."""
    return tree_snapshot(root, exclude=(LOCK_REL,))


class LockedRead:
    """A file object for the lock file that behaves like Windows while the byte range is locked: open succeeds,
    reading fails with PermissionError, everything else (seek, fileno, close) works."""

    def __init__(self, handle):
        self._handle = handle

    def _refuse(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    read = readall = readinto = readline = readlines = _refuse

    def __iter__(self):
        self._refuse()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._handle.close()
        return False

    def __getattr__(self, name):
        return getattr(self._handle, name)


@contextlib.contextmanager
def windows_lock_reads(monkeypatch, root: Path):
    """While active, any open() of the lock file returns LockedRead (builtins.open, io.open and Path.open)."""
    import builtins

    target = os.path.normcase(os.path.abspath(root / LOCK_REL))
    real_open = io.open

    def locked_open(file, *args, **kwargs):
        handle = real_open(file, *args, **kwargs)
        if isinstance(file, (str, os.PathLike)) and os.path.normcase(os.path.abspath(file)) == target:
            return LockedRead(handle)
        return handle

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", locked_open)
        patch.setattr(io, "open", locked_open)
        yield


def wait_for(predicate, seconds: float = 30.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not reached in time")


def run_phase(module, root: Path, spec: str, phase: str, model: str = "sonnet", reason: str = "Mechanical work.",
              *extra: str) -> Result:
    return drive(module, root, "run", "--spec", spec, "--phase", phase, "--model", model, "--reason", reason, *extra)


def status(module, root: Path) -> dict:
    result = drive(module, root, "status")
    assert result.code == 0, result.out
    return result.json


# ======================================================== T004 skeleton


@pytest.mark.parametrize("argv", [
    [], ["nope"], ["status", "extra"], ["brief", "--spec", "001-alpha"], ["brief", "--phase", "plan"],
    ["brief", "--spec", "001-alpha", "--phase", "deploy"], ["run", "--spec", "001-alpha", "--phase", "plan"],
    ["run", "--spec", "001-alpha", "--phase", "plan", "--model", "opus"],
    ["test"], ["test", "--spec", "001-alpha", "--spec", "001-alpha"], ["watch", "--minutes"],
    ["watch", "--minutes", "0"], ["watch", "--minutes", "116"], ["watch", "--minutes", "x"],
    ["cancel", "--now"], ["finalize", "x"], ["clear", "--all"], ["_drive"], ["_drive", "--token", "not-a-uuid"],
    ["run", "--spec", "001-alpha", "--phase", "plan", "--model", "bad model", "--reason", "r"],
    ["run", "--spec", "../x", "--phase", "plan", "--model", "opus", "--reason", "r"],
])
def test_usage_errors(drive_module, tmp_path, argv):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    before = tree_snapshot(root)
    result = drive(drive_module, root, *argv)
    assert result.code == 1
    data = result.json
    assert data["reason"] == "usage"
    assert result.err.decode("utf-8").strip() == data["error"]
    assert tree_snapshot(root) == before


@pytest.mark.parametrize("reason", ["x" * 301, "two\nlines", "   "])
def test_run_reason_length_and_lines_are_usage(drive_module, tmp_path, reason):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    result = run_phase(drive_module, root, "001-alpha", "plan", "opus", reason)
    assert (result.code, result.json["reason"]) == (1, "usage")
    assert not state_file(root).exists()


def test_output_is_one_utf8_json_object_with_lf_and_indent_two(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    result = drive(drive_module, root, "status")
    assert result.code == 0, result.describe()
    text = result.out.decode("utf-8")
    assert text.endswith("}\n") and "\r" not in text
    assert text == json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n"
    assert list(result.json) == ["speckit", "missing", "claude", "git", "branch", "own_dir", "running",
                                 "running_attempt", "driver", "last_attempt", "pending_finalize", "dirty", "leftovers",
                                 "specs", "next"]


def test_non_ascii_is_kept_as_is(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 0)}})
    write_state(root, blank_state(attempts=[attempt(reason="理由是設計工作。")]))
    out = drive(drive_module, root, "status").out.decode("utf-8")
    assert "\\u" not in out


@pytest.mark.parametrize("variable,value", [
    ("SDD_DRIVE_CLAUDE", "claude"), ("SDD_DRIVE_CLAUDE", "[]"), ("SDD_DRIVE_CLAUDE", "[1]"),
    ("SDD_DRIVE_CLAUDE", '{"a": 1}'), ("SDD_DRIVE_TEST_TIMING", "[]"), ("SDD_DRIVE_TEST_TIMING", '{"poll_seconds": 1}'),
    ("SDD_DRIVE_TEST_TIMING", '{"poll_seconds": "1", "margin_seconds": 1, "watch_seconds": 1}'),
    ("SDD_DRIVE_TEST_TIMING", "not json"),
])
def test_invalid_test_variables_are_usage(drive_module, tmp_path, monkeypatch, variable, value):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    monkeypatch.setenv(variable, value)
    result = drive(drive_module, root, "status")
    assert (result.code, result.json["reason"]) == (1, "usage")


def copy_skill_without_grill(tmp_path: Path) -> Path:
    skills = tmp_path / "skills-copy"
    shutil.copytree(SCRIPT.parent.parent, skills / "sdd-drive", ignore=shutil.ignore_patterns("__pycache__"))
    return skills / "sdd-drive" / "scripts" / "sdd_drive.py"


@pytest.mark.parametrize("argv", [["status"], ["brief", "--spec", "001-alpha", "--phase", "plan"], ["watch"],
                                  ["cancel"], ["test", "--spec", "001-alpha"], ["finalize"], ["clear"],
                                  ["run", "--spec", "001-alpha", "--phase", "plan", "--model", "opus", "--reason", "r"]])
def test_missing_sdd_grill_is_dependency_for_every_command(tmp_path, argv):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    script = copy_skill_without_grill(tmp_path)
    done = drive_real(root, *argv, script=script)
    assert done.returncode == 3, done.stdout
    data = json.loads(done.stdout.decode("utf-8"))
    assert data["reason"] == "dependency"
    assert data["error"] in done.stderr.decode("utf-8")


def test_real_script_runs_through_uv(tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    done = drive_real(root, "status")
    assert done.returncode == 0, done.stderr
    data = json.loads(done.stdout.decode("utf-8"))
    assert data["next"]["action"] == "run"
    text = done.stdout.decode("utf-8")
    assert str(tmp_path) not in text and str(Path.home()) not in text


def test_no_output_holds_an_absolute_home_path(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    outputs = [drive(drive_module, root, "status").text,
               drive(drive_module, root, "brief", "--spec", "001-alpha", "--phase", "plan").text]
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    outputs.append(run_phase(drive_module, root, "001-alpha", "plan").text)
    for text in outputs:
        assert os.environ["HOME"] not in text
        assert str(root) not in text


# ======================================================== T006 records


def test_own_dir_none_ours_conflict(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    assert status(drive_module, root)["own_dir"] == "none"
    write_state(root, blank_state())
    assert status(drive_module, root)["own_dir"] == "ours"
    (root / ".specify" / "sdd-drive" / "lock").write_bytes(b"")
    (root / ".specify" / "sdd-drive" / ".state.json.abc.tmp").write_bytes(b"{}")
    assert status(drive_module, root)["own_dir"] == "ours"
    for name in ("..gitignore.def.tmp", ".cancel.ghi.tmp"):  # every file atomic_write writes has its temporary file
        (root / ".specify" / "sdd-drive" / name).write_bytes(b"")
    assert status(drive_module, root)["own_dir"] == "ours"
    (root / ".specify" / "sdd-drive" / ".other.jkl.tmp").write_bytes(b"")
    assert drive(drive_module, root, "status").json["own_dir"] == "conflict"


@pytest.mark.parametrize("change", ["stranger", "gitignore", "folder"])
def test_own_dir_conflict(drive_module, tmp_path, change):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state())
    folder = root / ".specify" / "sdd-drive"
    if change == "stranger":
        (folder / "notes.txt").write_bytes(b"mine")
    elif change == "gitignore":
        (folder / ".gitignore").write_bytes(b"*\n")
    else:
        (folder / "sub").mkdir()
    before = tree_snapshot(root)
    result = drive(drive_module, root, "status")
    assert (result.code, result.json["reason"], result.json["own_dir"]) == (1, "conflict", "conflict")
    for argv in (["finalize"], ["clear"], ["test", "--spec", "001-alpha"], ["watch"], ["cancel"],
                 ["run", "--spec", "001-alpha", "--phase", "plan", "--model", "opus", "--reason", "r"]):
        result = drive(drive_module, root, *argv)
        assert (result.code, result.json["reason"]) == (1, "conflict"), argv
    assert tree_snapshot(root) == before


def test_own_dir_ignores_entries_that_vanish_while_it_is_read(drive_module, tmp_path, monkeypatch):
    """The driver renames its temporary file over state.json and removes cancel while watch and status list the folder.

    Before the fix such an entry was seen as "not a regular file" and every reader stopped with conflict.
    """
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state())
    folder = root / ".specify" / "sdd-drive"
    real_iterdir = Path.iterdir

    def iterdir_with_ghosts(self):
        yield from real_iterdir(self)
        if self == folder:
            yield folder / ".state.json.gone.tmp"
            yield folder / "cancel"

    monkeypatch.setattr(Path, "iterdir", iterdir_with_ghosts)
    drive_module.load_grill()
    assert drive_module.own_dir_state(root) == "ours"
    assert status(drive_module, root)["own_dir"] == "ours"


def test_own_dir_stays_ours_while_state_is_rewritten(drive_module, tmp_path):
    """A writer thread replaces state.json over and over; no read may see conflict or an unreadable file."""
    import threading

    root = make_project(tmp_path, specs={"001-alpha": {}})
    drive_module.load_grill()
    state = drive_module.empty_state([])
    drive_module.save_state(root, state)
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            drive_module.save_state(root, state)

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            assert drive_module.own_dir_state(root) == "ours"
            assert drive_module.load_state(root) is not None
    finally:
        stop.set()
        thread.join()


def test_state_reads_and_writes_wait_out_windows_sharing_violations(drive_module, tmp_path, monkeypatch):
    """Windows refuses to replace an open file and to open a file being replaced; both sides retry briefly."""
    root = make_project(tmp_path, specs={"001-alpha": {}})
    m = drive_module
    m.load_grill()
    m.save_state(root, m.empty_state([]))
    monkeypatch.setattr(m, "WINDOWS", True)
    failures = {"replace": 3, "read": 3}
    real_replace, real_read_bytes = os.replace, Path.read_bytes

    def busy_replace(src, dst):
        if failures["replace"]:
            failures["replace"] -= 1
            raise PermissionError(13, "Access is denied", str(dst))
        return real_replace(src, dst)

    def busy_read_bytes(self):
        if self.name == "state.json" and failures["read"]:
            failures["read"] -= 1
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(m.os, "replace", busy_replace)
    monkeypatch.setattr(Path, "read_bytes", busy_read_bytes)
    state = m.empty_state(["001-alpha"])
    m.save_state(root, state)
    assert m.load_state(root)["baseline"] == ["001-alpha"]
    assert failures == {"replace": 0, "read": 0}
    assert not [p.name for p in (root / ".specify" / "sdd-drive").iterdir() if p.name.endswith(".tmp")]


def test_permission_errors_are_not_retried_outside_windows(drive_module, tmp_path, monkeypatch):
    m = drive_module
    monkeypatch.setattr(m, "WINDOWS", False)
    seen = []

    def refuse():
        seen.append(1)
        raise PermissionError(13, "Permission denied")

    with pytest.raises(PermissionError):
        m.shared(refuse)
    assert seen == [1]
    monkeypatch.setattr(m, "WINDOWS", True)
    monkeypatch.setattr(m, "SHARING_SECONDS", 0.1)
    seen.clear()
    with pytest.raises(PermissionError):
        m.shared(refuse)
    assert len(seen) > 1


def test_first_write_creates_gitignore_and_state(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    assert run_phase(drive_module, root, "001-alpha", "plan").code == 0
    folder = root / ".specify" / "sdd-drive"
    assert (folder / ".gitignore").read_bytes() == OWN_GITIGNORE
    assert sorted(p.name for p in folder.iterdir()) == [".gitignore", "lock", "state.json"]
    data = read_state(root)
    assert list(data) == ["tool", "schema", "attempts", "baseline", "baseline_reset", "launch", "driver", "tests"]
    assert git_run(root, "status", "--porcelain", "--ignored", ".specify/sdd-drive") .startswith("!!")


def test_state_write_replaces_through_a_temporary_file(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state())
    before = state_file(root).read_bytes()
    drive_module.load_grill()

    def broken(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(drive_module.os, "replace", broken)
    result = drive(drive_module, root, "clear")
    assert (result.code, result.json["reason"]) == (1, "os-error")
    assert state_file(root).read_bytes() == before
    assert [p.name for p in state_file(root).parent.iterdir() if p.name.endswith(".tmp")] == []


def test_atomic_write_leaves_no_temporary_file(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    drive(drive_module, root, "clear")
    assert [p.name for p in state_file(root).parent.iterdir() if p.name.endswith(".tmp")] == []


BAD_FIELDS = [
    ("tool", lambda s: s.update(tool="other")),
    ("schema", lambda s: s.update(schema=2)),
    ("attempts[1].id", lambda s: s["attempts"][1].update(id=1)),
    ("attempts[0].spec", lambda s: s["attempts"][0].update(spec="001-a/b")),
    ("attempts[0].spec", lambda s: s["attempts"][0].update(spec="001-a\\b")),
    ("attempts[0].phase", lambda s: s["attempts"][0].update(phase="deploy")),
    ("attempts[0].session_id", lambda s: s["attempts"][0].update(session_id="abc")),
    ("attempts[0].model", lambda s: s["attempts"][0].update(model="bad model")),
    ("attempts[0].model_used", lambda s: s["attempts"][0].update(model_used=["bad model"])),
    ("attempts[0].reason", lambda s: s["attempts"][0].update(reason="")),
    ("attempts[0].reason", lambda s: s["attempts"][0].update(reason="token=" + SECRET_VALUE)),
    ("attempts[0].started_at", lambda s: s["attempts"][0].update(started_at="2026-11-21 10:00")),
    ("attempts[0].ended_at", lambda s: s["attempts"][0].update(ended_at=None)),
    ("attempts[0].outcome", lambda s: s["attempts"][0].update(outcome="great")),
    ("attempts[0].detail.code", lambda s: s["attempts"][0].update(detail={"code": "x", "paths": [], "text": None})),
    ("attempts[0].detail.text", lambda s: s["attempts"][0].update(detail={"code": "api-error", "paths": [], "text": SECRET_VALUE})),
    ("attempts[0].detail.paths[0]", lambda s: s["attempts"][0].update(detail={"code": "uncommitted", "paths": [SECRET_VALUE], "text": None})),
    ("attempts[0].report", lambda s: s["attempts"][0].update(report={"status": "maybe", "summary": "x"})),
    ("attempts[0].report.summary", lambda s: s["attempts"][0].update(report={"status": "completed", "summary": SECRET_VALUE})),
    ("attempts[0].worktree", lambda s: s["attempts"][0].update(worktree="sha256:xyz")),
    ("attempts[0].task_ids", lambda s: s["attempts"][0].update(task_ids=["X1"])),
    ("attempts[0].tasks_hash", lambda s: s["attempts"][0].update(tasks_hash="abc")),
    ("attempts[0].limit", lambda s: s["attempts"][0].update(limit={"waitable": True})),
    ("attempts[0].limit.types", lambda s: s["attempts"][0].update(limit={"waitable": False, "types": ["daily"], "resets_at": None, "overage_status": None})),
    ("attempts[0].auto_resume", lambda s: s["attempts"][0].update(auto_resume="soon")),
    ("attempts[0].auto", lambda s: s["attempts"][0].update(auto="no")),
    ("launch", lambda s: s.update(launch={"token": "x"})),
    ("driver", lambda s: s.update(driver={"token": UUID1})),
    ("baseline", lambda s: s.update(baseline=["001-alpha", "001-alpha"])),
    ("baseline_reset", lambda s: s.update(baseline_reset="yes")),
    ("tests[0].spec", lambda s: s["tests"][0].update(spec="nonumber")),
    ("tests[0].tasks_hash", lambda s: s["tests"][0].update(tasks_hash=None)),
    ("tests[0].head", lambda s: s["tests"][0].update(head="abc")),
    ("tests[0].command", lambda s: s["tests"][0].update(command="pytest --token=" + SECRET_VALUE)),
    ("tests[0].exit_code", lambda s: s["tests"][0].update(exit_code="0")),
]


@pytest.mark.parametrize("path,change", BAD_FIELDS)
def test_invalid_field_is_state_unreadable_without_the_value(drive_module, tmp_path, path, change):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    state = blank_state(attempts=[attempt(1), attempt(2, phase="tasks")],
                        tests=[test_record("001-alpha", "sha256:" + "0" * 64)])
    change(state)
    write_state(root, state)
    result = drive(drive_module, root, "status")
    assert (result.code, result.json["reason"]) == (3, "state-unreadable")
    assert result.json["detail"] == path
    assert SECRET_VALUE not in result.text


def test_unparsable_state_is_state_unreadable(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state())
    state_file(root).write_bytes(b"{not json")
    for argv in (["status"], ["finalize"], ["watch"], ["test", "--spec", "001-alpha"],
                 ["run", "--spec", "001-alpha", "--phase", "plan", "--model", "opus", "--reason", "r"]):
        result = drive(drive_module, root, *argv)
        assert (result.code, result.json["reason"]) == (3, "state-unreadable"), argv


def test_valid_record_with_every_field_reads_back(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    full = attempt(1, phase="tasks", outcome="usage-limit", detail={"code": "usage-limit", "paths": [], "text": "hit"},
                   report={"status": "completed", "summary": "s"}, worktree="sha256:" + "a" * 64, task_ids=["T001"],
                   tasks_hash="sha256:" + "b" * 64, limit={"waitable": True, "types": ["five_hour"],
                                                            "resets_at": T1, "overage_status": "rejected"},
                   auto_resume="cancelled", permission_denials=["WebFetch"])
    write_state(root, blank_state(attempts=[full], tests=[test_record("001-alpha", "sha256:" + "c" * 64, head="d" * 40)]))
    assert drive(drive_module, root, "status").code == 0


def test_secrets_from_outside_are_replaced_before_writing(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"do": [], "report": {"status": "failed", "summary": "used " + SECRET_VALUE,
                                                 "failure": {"kind": "tooling", "step": "token=" + SECRET_VALUE,
                                                             "reason": SECRET_VALUE}}})
    result = run_phase(drive_module, root, "001-alpha", "plan")
    assert result.code == 0, result.describe()
    raw = state_file(root).read_text(encoding="utf-8")
    assert SECRET_VALUE not in raw and SECRET_VALUE not in result.text
    report = read_state(root)["attempts"][0]["report"]
    assert report["summary"] == SECRET_TEXT and report["failure"]["reason"] == SECRET_TEXT
    assert status(drive_module, root)["specs"][0]["failures"] == {"plan": 1}


def test_error_text_secret_is_replaced(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"do": [], "result": {"is_error": True, "api_error_status": 401,
                                                 "result": "bad key " + SECRET_VALUE}})
    result = run_phase(drive_module, root, "001-alpha", "plan")
    assert result.watched["attempts"][0]["detail"]["text"] == SECRET_TEXT
    assert SECRET_VALUE not in state_file(root).read_text(encoding="utf-8")


def test_reason_secret_is_refused_and_nothing_written(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    before = tree_snapshot(root)
    result = run_phase(drive_module, root, "001-alpha", "plan", "opus", "use token=" + SECRET_VALUE)
    assert (result.code, result.json["reason"]) == (1, "secret")
    assert SECRET_VALUE not in result.text
    assert tree_snapshot(root) == before


def test_baseline_is_computed_before_the_first_write_and_frozen_after(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 2)},
                                         "002-beta": {"plan": True, "tasks": (2, 1)}})
    first = status(drive_module, root)
    assert [row["baseline"] for row in first["specs"]] == [True, False]
    assert drive(drive_module, root, "test", "--spec", "001-alpha").code == 0
    assert read_state(root)["baseline"] == ["001-alpha"]
    assert [row["baseline"] for row in status(drive_module, root)["specs"]] == [True, False]
    # 002 is finished by hand later: it never joins the frozen baseline.
    add_spec(root, "002-beta", plan=True, tasks=(2, 2))
    commit_all(root)
    assert read_state(root)["baseline"] == ["001-alpha"]
    assert [row["baseline"] for row in status(drive_module, root)["specs"]] == [True, False]


def test_other_tools_state_file_and_specify_gitignore_are_untouched(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_tree(root, {".specify/sdd-drive-state.json": "{broken", ".specify/.gitignore": "sdd-drive-state.json\n"})
    commit_all(root)
    before = {p: (root / p).read_bytes() for p in (".specify/sdd-drive-state.json", ".specify/.gitignore")}
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    assert status(drive_module, root)["next"]["action"] == "run"
    assert run_phase(drive_module, root, "001-alpha", "plan").code == 0
    drive(drive_module, root, "clear")
    assert {p: (root / p).read_bytes() for p in before} == before


# ======================================================== T008 lock


def test_held_lock_reports_running_and_refuses_writers(drive_module, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}})
    write_state(root, blank_state(attempts=[attempt(1, phase="implement")]))
    with hold_lock(root):
        data = status(drive_module, root)
        assert data["running"] is True and data["next"]["action"] == "wait"
        before = snapshot_without_lock(root)
        assert LOCK_REL not in before and ".specify/sdd-drive/state.json" in before
        for argv in (["run", "--spec", "001-alpha", "--phase", "check", "--model", "opus", "--reason", "r"],
                     ["test", "--spec", "001-alpha"], ["finalize"], ["clear"]):
            result = drive(drive_module, root, *argv)
            assert (result.code, result.json["reason"]) == (1, "running"), argv
        assert snapshot_without_lock(root) == before
        assert (root / LOCK_REL).is_file()
    assert status(drive_module, root)["running"] is False


def test_windows_lock_reads_refuses_like_windows(tmp_path, monkeypatch):
    """The simulation itself: open succeeds, read fails, other files are untouched, tree_snapshot fails without
    exclude and succeeds with it."""
    root = tmp_path / "proj"
    write_tree(root, {LOCK_REL: "", "other.txt": "x"})
    with windows_lock_reads(monkeypatch, root):
        with open(root / LOCK_REL, "rb") as handle:
            handle.seek(0)
            assert isinstance(handle.fileno(), int)
            with pytest.raises(PermissionError):
                handle.read()
        with pytest.raises(PermissionError):
            (root / LOCK_REL).read_bytes()
        assert (root / "other.txt").read_bytes() == b"x"
        with pytest.raises(PermissionError):
            tree_snapshot(root)
        assert set(tree_snapshot(root, exclude=(LOCK_REL,))) == {".specify", ".specify/sdd-drive", "other.txt"}


def test_script_never_reads_the_lock_file_while_it_is_held(drive_module, tmp_path, monkeypatch):
    """On Windows a locked byte range cannot be read; the fingerprint, the tree hashes and status must skip it."""
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}})
    write_state(root, blank_state(attempts=[attempt(1, phase="implement")]))
    drive_module.load_grill()
    with hold_lock(root):
        assert (root / LOCK_REL).is_file()
        (root / "specs" / "001-alpha" / "dirty.txt").write_bytes(b"x")
        assert drive_module.worktree_fingerprint(root).startswith("sha256:")
        hashes = drive_module.tree_hashes(root, True)
        assert not any(k.startswith(".specify/sdd-drive") for k in hashes)
        assert drive_module.own_dir_state(root) == "ours"
        assert status(drive_module, root)["running"] is True


class FakeMsvcrt:
    """msvcrt.locking on top of flock, so the Windows branch of Lock runs here; it also checks how it is called."""
    LK_UNLCK, LK_NBLCK = 0, 2

    def __init__(self):
        self.calls = []

    def locking(self, fd, mode, nbytes):
        import fcntl

        self.calls.append((mode, nbytes, os.lseek(fd, 0, os.SEEK_CUR)))
        assert nbytes == 1 and os.lseek(fd, 0, os.SEEK_CUR) == 0, "lock byte 0 of the file"
        if mode == self.LK_NBLCK:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PermissionError(13, "Permission denied") from None
        elif mode == self.LK_UNLCK:
            fcntl.flock(fd, fcntl.LOCK_UN)
        else:
            raise AssertionError(f"unexpected mode {mode}")


def test_windows_lock_branch(drive_module, tmp_path, monkeypatch):
    """Elsewhere FakeMsvcrt stands in for msvcrt; on Windows the real one is used."""
    m = drive_module
    m.load_grill()
    root = make_project(tmp_path, specs={"001-alpha": {}})
    fake = FakeMsvcrt()
    if os.name != "nt":
        monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(m, "WINDOWS", True)
    assert m.lock_held(root) is False and not (root / LOCK_REL).exists()  # the probe never creates the file
    first = m.Lock(root)
    assert first.try_acquire() is True
    assert m.lock_held(root) is True
    assert m.Lock(root).try_acquire() is False
    first.release()
    assert m.lock_held(root) is False
    second = m.Lock(root)
    assert second.acquire(1) is True
    second.release()
    if os.name != "nt":
        assert {mode for mode, _, _ in fake.calls} == {fake.LK_NBLCK, fake.LK_UNLCK}


class FakePopen:
    """Records the creation flags; refuses CREATE_BREAKAWAY_FROM_JOB the way a job object without breakaway does."""

    def __init__(self, log, refuse_breakaway=True, refuse_all=False, code=0):
        self.log, self.refuse_breakaway, self.refuse_all, self.code = log, refuse_breakaway, refuse_all, code

    def __call__(self, args, **kwargs):
        flags = kwargs.get("creationflags", 0)
        self.log.append(flags)
        if self.refuse_all or (self.refuse_breakaway and flags & 0x01000000):
            raise OSError(5, "Access is denied")
        assert "start_new_session" not in kwargs
        return types.SimpleNamespace(wait=lambda timeout=None: self.code)


def test_start_driver_windows_flags_and_breakaway_fallback(drive_module, tmp_path, monkeypatch):
    m = drive_module
    monkeypatch.setattr(m, "WINDOWS", True)
    log: list = []
    monkeypatch.setattr(m.subprocess, "Popen", FakePopen(log))
    assert m.start_driver(tmp_path, UUID1) is True
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, first with CREATE_BREAKAWAY_FROM_JOB, then without it
    assert log == [0x01000208, 0x208]
    log.clear()
    monkeypatch.setattr(m.subprocess, "Popen", FakePopen(log, refuse_breakaway=False))
    assert m.start_driver(tmp_path, UUID1) is True and log == [0x01000208]
    log.clear()
    monkeypatch.setattr(m.subprocess, "Popen", FakePopen(log, refuse_all=True))
    assert m.start_driver(tmp_path, UUID1) is False and log == [0x01000208, 0x208]
    monkeypatch.setattr(m.subprocess, "Popen", FakePopen([], refuse_breakaway=False, code=1))
    assert m.start_driver(tmp_path, UUID1) is False


def test_driver_starter_windows_branch(drive_module, monkeypatch):
    """The middle process's own Windows branch, run in this process with os.name and Popen replaced."""
    log: list = []
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", FakePopen(log))
        patch.setattr(sys, "argv", ["-c", "python", "sdd_drive.py", "_drive", "--token", UUID1])
        patch.setattr(os, "name", "nt")
        exec(compile(drive_module.DRIVER_STARTER, "<starter>", "exec"), {"__name__": "__main__"})
    assert log == [0x01000208, 0x208]


def test_lock_is_released_when_the_holder_is_killed(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    with hold_lock(root) as holder:
        assert status(drive_module, root)["running"] is True
        holder.kill()
        holder.wait(timeout=30)
        assert status(drive_module, root)["running"] is False


def test_status_does_not_create_the_lock(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    before = tree_snapshot(root)
    status(drive_module, root)
    assert tree_snapshot(root) == before


def iso(seconds_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


def test_recent_launch_counts_as_running(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state(attempts=[attempt(1, outcome=None)], launch={"token": UUID2, "at": iso(5)}))
    data = status(drive_module, root)
    assert data["running"] is True and data["next"]["action"] == "wait" and data["pending_finalize"] is False
    for argv in (["run", "--spec", "001-alpha", "--phase", "plan", "--model", "opus", "--reason", "r"],
                 ["finalize"], ["clear"]):
        assert drive(drive_module, root, *argv).json["reason"] == "running", argv


def test_old_launch_without_lock_is_a_failed_start(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state(attempts=[attempt(1, outcome=None)], launch={"token": UUID2, "at": iso(61)}))
    data = status(drive_module, root)
    assert data["running"] is False and data["pending_finalize"] is True
    assert data["next"]["action"] == "finalize"
    watched = drive(drive_module, root, "watch")
    assert watched.code == 0 and watched.watched["status"] == "launch-failed"


# ======================================================== T010 git and protected files


@pytest.fixture
def m(drive_module):
    drive_module.load_grill()
    return drive_module


def test_git_and_non_git_projects(m, tmp_path):
    assert m.is_git(make_project(tmp_path, "a")) is True
    plain = make_project(tmp_path, "b", git=False, specs={"001-alpha": {}})
    assert m.is_git(plain) is False
    data = status(m, plain)
    assert data["git"] is False and data["dirty"] == [] and data["branch"] is None and data["next"]["branch"] is None


def test_dirty_paths_exclude_feature_json_our_folder_and_ignored(m, tmp_path):
    root = make_project(tmp_path)
    write_tree(root, {".gitignore": "build/\n"})
    commit_all(root)
    write_tree(root, {".specify/feature.json": "{}", ".specify/sdd-drive/.gitignore": OWN_GITIGNORE.decode(),
                      "build/out.bin": "x", "new dir/untracked.txt": "u", "README.md": "changed"})
    assert m.dirty_paths(root) == ["README.md", "new dir/untracked.txt"]


def test_dirty_secret_paths_are_hidden_in_status(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    commit_all(root)
    write_tree(root, {f"notes-{SECRET_VALUE}.txt": "x"})
    data = status(m, root)
    assert data["dirty"] == ["(not shown)"]


def test_worktree_fingerprint(m, tmp_path):
    root = make_project(tmp_path)
    clean = m.worktree_fingerprint(root)
    assert clean.startswith("sha256:") and len(clean) == 71
    write_tree(root, {"a.txt": "one\n"})
    first = m.worktree_fingerprint(root)
    assert first != clean and first == m.worktree_fingerprint(root)
    write_tree(root, {"a.txt": "two\n"})
    assert m.worktree_fingerprint(root) != first
    write_tree(root, {"a.txt": "one\r\n"})
    crlf = m.worktree_fingerprint(root)
    assert crlf == m.worktree_fingerprint(root)
    assert m.worktree_fingerprint(make_project(tmp_path, "plain", git=False)) is None


def test_remote_refs_snapshot_changes_on_push(m, tmp_path):
    root = make_project(tmp_path)
    bare_remote(tmp_path, root)
    before = m.remote_refs(root)
    assert "refs/remotes/origin/" in before
    write_tree(root, {"x.txt": "x"})
    commit_all(root)
    git_run(root, "push", "--quiet", "origin", "HEAD")
    assert m.remote_refs(root) != before


def branch_of(root):
    return git_run(root, "rev-parse", "--abbrev-ref", "HEAD").strip()


def test_branch_create_stay_switch_and_diverged(m, tmp_path):
    root = make_project(tmp_path)
    start = branch_of(root)
    m.prepare_branch(root, "001-alpha")
    assert branch_of(root) == "001-alpha"
    m.prepare_branch(root, "001-alpha")
    assert branch_of(root) == "001-alpha"
    write_tree(root, {"a.txt": "a"})
    commit_all(root)
    m.prepare_branch(root, "002-beta")  # created from the current HEAD: stacked on 001
    assert branch_of(root) == "002-beta"
    assert git_run(root, "merge-base", "--is-ancestor", "001-alpha", "002-beta") == ""
    git_run(root, "switch", "--quiet", "-c", "003-gamma", start)
    git_run(root, "switch", "--quiet", "001-alpha")
    # 003-gamma is at the start commit, HEAD (001-alpha) is not its ancestor: diverged.
    head_before = head_of(root)
    with pytest.raises(m.Failure) as error:
        m.prepare_branch(root, "003-gamma")
    assert error.value.reason == "branch-diverged"
    assert branch_of(root) == "001-alpha" and head_of(root) == head_before
    git_run(root, "switch", "--quiet", start)
    m.prepare_branch(root, "001-alpha")  # start is an ancestor of 001-alpha
    assert branch_of(root) == "001-alpha"
    assert start != "001-alpha"


@pytest.mark.parametrize("existing,expected", [
    (None, {"feature_directory": "specs/001-alpha"}),
    ('{"feature_directory": "specs/000-old", "other": 1}', {"feature_directory": "specs/001-alpha", "other": 1}),
    ("[1, 2]", {"feature_directory": "specs/001-alpha"}),
    ("not json", {"feature_directory": "specs/001-alpha"}),
])
def test_feature_json_keeps_other_keys(m, tmp_path, existing, expected):
    root = make_project(tmp_path)
    if existing is not None:
        write_tree(root, {".specify/feature.json": existing})
    m.set_feature_directory(root, "001-alpha")
    assert json.loads((root / ".specify/feature.json").read_text(encoding="utf-8")) == expected


@pytest.mark.parametrize("rel", [".specify/memory/constitution.md", "specs/001-alpha/spec.md",
                                 ".specify/templates/plan-template.md", ".specify/scripts/bash/common.sh",
                                 ".claude/skills/speckit-plan/SKILL.md", ".claude/skills/speckit-new/extra.md"])
def test_protected_files_changes_are_listed(m, tmp_path, rel):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    before = m.protected_hashes(root)
    write_tree(root, {rel: "changed\n"})
    assert m.changed_keys(before, m.protected_hashes(root)) == [rel]


def test_unprotected_files_are_not_listed(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    before = m.protected_hashes(root)
    write_tree(root, {"specs/001-alpha/plan.md": "x", ".claude/skills/other/SKILL.md": "x", "src/a.py": "x"})
    assert m.changed_keys(before, m.protected_hashes(root)) == []


# ======================================================== T012 spec state


def test_only_numbered_spec_folders_in_number_order(m, tmp_path):
    root = make_project(tmp_path, specs={"010-ten": {}, "002-two": {}, "20261121-101010-stamp": {}})
    write_tree(root, {"specs/notes/spec.md": "x", "specs/005-empty/readme.md": "x"})
    assert m.spec_dirs(root) == ["002-two", "010-ten", "20261121-101010-stamp"]


def test_plan_not_generated_cases(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    assert m.plan_generated(root, "001-alpha") is False
    template = (root / ".specify/templates/plan-template.md").read_text(encoding="utf-8")
    write_tree(root, {"specs/001-alpha/plan.md": template})
    assert m.plan_generated(root, "001-alpha") is False
    write_tree(root, {"specs/001-alpha/plan.md": template.replace("\n", "\r\n")})
    assert m.plan_generated(root, "001-alpha") is False
    write_tree(root, {"specs/001-alpha/plan.md": "# Implementation Plan: [FEATURE]\n\nfilled a bit\n"})
    assert m.plan_generated(root, "001-alpha") is False
    write_tree(root, {"specs/001-alpha/plan.md": plan_text("001-alpha")})
    assert m.plan_generated(root, "001-alpha") is True


def test_tasks_not_generated_cases(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    assert m.tasks_generated(root, "001-alpha") is False
    template = (root / ".specify/templates/tasks-template.md").read_text(encoding="utf-8")
    write_tree(root, {"specs/001-alpha/tasks.md": template})
    assert m.tasks_generated(root, "001-alpha") is False
    write_tree(root, {"specs/001-alpha/tasks.md": "# Tasks: [FEATURE NAME]\n\n- [ ] T001 x\n"})
    assert m.tasks_generated(root, "001-alpha") is False
    write_tree(root, {"specs/001-alpha/tasks.md": "# Tasks: alpha\n\nNo task lines yet.\n"})
    assert m.tasks_generated(root, "001-alpha") is False
    write_tree(root, {"specs/001-alpha/tasks.md": tasks_text("001-alpha", 2)})
    assert m.tasks_generated(root, "001-alpha") is True


def test_task_line_format(m, tmp_path):
    text = "\n".join(["- [ ] T001 a", "- [x] T002 b", "  - [X] T0003 c", "- [ ] T01 too short", "* [ ] T004 star",
                      "- [ ]T005 no space", "- [x] T006"]) + "\n"
    assert m.task_entries(text) == [("T001", False), ("T002", True), ("T0003", True), ("T006", True)]


@pytest.mark.parametrize("specs,expected", [
    ({}, ("not-started", "plan", 0, 0)),
    ({"plan": True}, ("planned", "tasks", 0, 0)),
    ({"plan": True, "tasks": (3, 0)}, ("tasked", "implement", 3, 3)),
    ({"plan": True, "tasks": (3, 1)}, ("implementing", "implement", 3, 2)),
])
def test_states_before_all_tasks_are_checked(m, tmp_path, specs, expected):
    root = make_project(tmp_path, specs={"001-alpha": specs})
    row = status(m, root)["specs"][0]
    assert (row["state"], row["next_phase"], row["tasks_total"], row["tasks_open"]) == expected
    assert list(row) == ["spec", "state", "next_phase", "baseline", "tasks_total", "tasks_open", "failures"]


@pytest.mark.parametrize("line,expected", [
    ("**Testing**: `uv run --with pytest pytest` and more `x`", ("uv run --with pytest pytest", None)),
    ("**Testing**: pytest", (None, "missing")),
    ("**Testing**: ``", (None, "placeholder")),
    ("**Testing**: `  `", (None, "placeholder")),
    ("**Testing**: `N/A`", (None, "placeholder")),
    ("**Testing**: `None`", (None, "placeholder")),
    ("**Testing**: `tbd`", (None, "placeholder")),
    ("**Testing**: `pytest --password=hunter2`", (None, "secret")),
    ("No testing line", (None, "missing")),
])
def test_test_command_extraction(m, tmp_path, line, expected):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": f"# Plan: alpha\n\n{line}\n"}})
    assert m.test_command(root, "001-alpha") == expected


def test_tasks_hash_format_and_newline_normalisation(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 0)}})
    value = m.tasks_hash(root, "001-alpha")
    assert value.startswith("sha256:") and len(value) == 71
    path = root / "specs/001-alpha/tasks.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert m.tasks_hash(root, "001-alpha") == value


def test_state_is_recomputed_from_the_files_every_time(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 0)}})
    assert status(m, root)["specs"][0]["state"] == "tasked"
    add_spec(root, "001-alpha", plan=True, tasks=(2, 1))
    assert status(m, root)["specs"][0]["state"] == "implementing"


# ======================================================== T014 status


def test_status_prerequisite_order(m, tmp_path, monkeypatch):
    plain = tmp_path / "nothing"
    plain.mkdir()
    result = drive(m, plain, "status")
    assert (result.code, result.json["reason"], result.json["speckit"]) == (3, "speckit-missing", "missing")
    assert list(result.json)[:15] == ["speckit", "missing", "claude", "git", "branch", "own_dir", "running",
                                      "running_attempt", "driver", "last_attempt", "pending_finalize", "dirty",
                                      "leftovers", "specs", "next"]

    partial = make_project(tmp_path, "partial", skills=("speckit-plan",))
    result = drive(m, partial, "status")
    assert (result.code, result.json["reason"]) == (3, "speckit-incomplete")
    assert result.json["missing"] == ["speckit-tasks", "speckit-implement", "speckit-converge"]

    no_converge = make_project(tmp_path, "no-converge", skills=("speckit-plan", "speckit-tasks", "speckit-implement"),
                               specs={"001-alpha": {}})
    result = drive(m, no_converge, "status")
    assert (result.code, result.json["reason"]) == (3, "speckit-incomplete")
    assert result.json["missing"] == ["speckit-converge"]
    result = run_phase(m, no_converge, "001-alpha", "plan")
    assert (result.code, result.json["reason"], result.json["missing"]) == (3, "speckit-incomplete", ["speckit-converge"])

    empty = make_project(tmp_path, "empty")
    assert drive(m, empty, "status").json["reason"] == "no-specs"

    root = make_project(tmp_path, "full", specs={"001-alpha": {}})
    monkeypatch.delenv("SDD_DRIVE_CLAUDE")
    monkeypatch.setenv("PATH", str(tmp_path / "no-bin"))
    result = drive(m, root, "status")
    assert (result.code, result.json["reason"], result.json["claude"]) == (3, "claude-missing", "missing")


def test_claude_found_on_path(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    name = "claude.exe" if os.name == "nt" else "claude"
    (bin_dir / name).write_bytes(b"#!/bin/sh\n")
    (bin_dir / name).chmod(0o755)
    monkeypatch.delenv("SDD_DRIVE_CLAUDE")
    monkeypatch.setenv("PATH", str(bin_dir))
    assert drive(m, root, "status").json["claude"] == "ok"


def test_conflict_is_reported_after_claude_and_before_state(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state())
    state_file(root).write_bytes(b"broken")
    (root / ".specify/sdd-drive/stranger").write_bytes(b"x")
    assert drive(m, root, "status").json["reason"] == "conflict"


def test_next_is_decided_by_the_first_unfinished_spec_only(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}, "002-beta": {}})
    data = status(m, root)
    assert data["next"]["spec"] == "001-alpha" and data["next"]["phase"] == "tasks"
    assert [row["spec"] for row in data["specs"]] == ["001-alpha", "002-beta"]


def test_next_run_fields_and_hints(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    write_tree(root, {"specs/001-alpha/contracts/cli.md": "x", "specs/001-alpha/contracts/skill.md": "y"})
    commit_all(root)
    write_state(root, blank_state(attempts=[attempt(1, phase="tasks", outcome="failed",
                                                    report={"status": "failed", "summary": "s",
                                                            "failure": {"kind": "other", "step": "a", "reason": "b"}})]))
    nxt = status(m, root)["next"]
    assert list(nxt) == ["action", "spec", "phase", "branch", "session_id", "model", "failures", "last_outcome",
                         "limit", "auto_resume", "test_command", "covers", "hints"]
    assert (nxt["action"], nxt["spec"], nxt["phase"], nxt["branch"]) == ("run", "001-alpha", "tasks", "001-alpha")
    assert nxt["failures"] == {"tasks": 1}
    plan_bytes = (root / "specs/001-alpha/plan.md").stat().st_size
    assert nxt["hints"] == {"requirements": 3, "user_stories": 2, "plan_bytes": plan_bytes, "contracts": 2,
                            "tasks_total": 0, "tasks_open": 0, "phase_failures": 1, "models_used_this_run": ["opus"]}


def test_next_none_when_every_spec_is_done(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}})
    write_state(root, blank_state(baseline=["001-alpha"],
                                  tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"))]))
    data = status(m, root)
    assert data["specs"][0]["state"] == "done"
    assert data["next"] == {key: ("none" if key == "action" else None) for key in data["next"]}


def test_status_git_false_dirty_and_leftovers(m, tmp_path):
    plain = make_project(tmp_path, "plain", git=False, specs={"001-alpha": {}})
    data = status(m, plain)
    assert (data["git"], data["dirty"], data["leftovers"]) == (False, [], False)
    root = make_project(tmp_path, "repo", specs={"001-alpha": {}})
    write_tree(root, {"mine.txt": "x"})
    data = status(m, root)
    assert data["dirty"] == ["mine.txt"] and data["leftovers"] is False


def test_status_writes_nothing(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 1)}})
    write_state(root, blank_state(attempts=[attempt(1)]))
    before = tree_snapshot(root)
    for _ in range(2):
        status(m, root)
    assert tree_snapshot(root) == before


def test_last_attempt_and_running_attempt(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state(attempts=[attempt(1, outcome="interrupted", detail={"code": "no-result", "paths": [], "text": None}),
                                            attempt(2, outcome=None, started_at=T1)]))
    with hold_lock(root):
        data = status(m, root)
    assert data["last_attempt"] == {"spec": "001-alpha", "phase": "plan", "outcome": "interrupted", "auto": False,
                                    "limit": None, "auto_resume": None, "ended_at": T1}
    assert data["running_attempt"] == {"spec": "001-alpha", "phase": "plan", "model": "opus", "started_at": T1,
                                       "limit": None, "auto_resume": None}
    assert data["next"]["action"] == "wait" and data["next"]["spec"] == "001-alpha"


# ======================================================== T015 brief

BRIEF_COMMON_ITEMS = [
    "Spec directory: specs/001-alpha", "Phase: {phase}", "Branch: 001-alpha", "Do only the {phase} phase",
    "Skill tool", "`{skill}`", "MUST NOT write or edit the artifacts", "Do not ask questions",
    "do not wait for approval", "constitution", "write down the reason", '"requirements"',
    "MUST NOT modify spec.md or the constitution", ".specify/templates/", ".specify/scripts/", "`speckit-*` skill",
    "folders of other specs", ".specify/sdd-drive/", "MUST NOT push", "switch or create branches", "amend",
    "rebase", "reset", "merge", "stash", "clean", "Never write secret values", "structured output", '"status"',
    '"summary"', '"failure"', "Project root: . (the current directory)",
]
BRIEF_PHASE_ITEMS = {
    "plan": ["**Testing**:", "first backtick span", "same way on Windows and Linux", "Commit to the current branch",
             "Leave no uncommitted changes"],
    "tasks": ["Notes", "`- [ ] T001", "need the maintainer or a push", "Commit to the current branch"],
    "implement": ["only the unchecked tasks", "Check a task off as soon as it is done", "MUST NOT delete, rewrite or merge",
                  '"blocked-task"', "run the test command and make it pass", "`TESTCMD`",
                  "must not depend on the order"],
    "check": ["only write allowed is the Convergence section", "end of specs/001-alpha/tasks.md",
              "MUST NOT modify code, tests, plan.md, spec.md", "MUST NOT check, rewrite, delete or renumber",
              "MUST NOT fix the problems", "one commit that holds only that file",
              "MUST NOT create any commit or change any file", '"convergence"', '"converged"', '"tasks-appended"'],
}
SKILL_OF = {"plan": "speckit-plan", "tasks": "speckit-tasks", "implement": "speckit-implement", "check": "speckit-converge"}


@pytest.mark.parametrize("phase", ["plan", "tasks", "implement", "check"])
def test_brief_holds_every_required_item(m, tmp_path, phase):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "command": "TESTCMD"}})
    before = tree_snapshot(root)
    result = drive(m, root, "brief", "--spec", "001-alpha", "--phase", phase)
    assert result.code == 0, result.describe()
    text = result.text
    for item in BRIEF_COMMON_ITEMS + BRIEF_PHASE_ITEMS[phase]:
        assert item.format(phase=phase, skill=SKILL_OF[phase]) in text, item
    assert str(root) not in text and str(tmp_path) not in text
    assert "Resuming" not in text
    assert tree_snapshot(root) == before


def test_brief_without_git_says_not_to_commit(m, tmp_path):
    root = make_project(tmp_path, git=False, specs={"001-alpha": {"plan": True}})
    text = drive(m, root, "brief", "--spec", "001-alpha", "--phase", "implement").text
    assert "not a git repository: do not commit" in text and "Commit to the current branch" not in text


def test_brief_resume_asks_to_check_the_files_first(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    text = m.brief_text(root, "001-alpha", "implement", resume=True)
    assert "First check the current state of the files again" in text and "do not redo" in text


def test_brief_unknown_spec_is_usage(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    result = drive(m, root, "brief", "--spec", "009-missing", "--phase", "plan")
    assert (result.code, result.json["reason"]) == (1, "usage")


# ======================================================== T016 run: preparation


def test_run_prerequisite_failures_write_no_attempt(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, skills=("speckit-plan",), specs={"001-alpha": {}})
    result = run_phase(m, root, "001-alpha", "plan")
    assert (result.code, result.json["reason"]) == (3, "speckit-incomplete")
    root = make_project(tmp_path, "b", specs={"001-alpha": {}})
    monkeypatch.delenv("SDD_DRIVE_CLAUDE")
    monkeypatch.setenv("PATH", str(tmp_path / "no-bin"))
    result = run_phase(m, root, "001-alpha", "plan")
    assert (result.code, result.json["reason"]) == (3, "claude-missing")
    assert not (root / ".specify/sdd-drive").exists()


def test_run_not_next(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}, "002-beta": {}})
    before = tree_snapshot(root)
    for spec, phase in (("002-beta", "plan"), ("001-alpha", "tasks"), ("009-none", "plan")):
        result = run_phase(m, root, spec, phase)
        assert (result.code, result.json["reason"]) == (1, "not-next"), (spec, phase)
    result = run_phase(m, root, "001-alpha", "plan", "opus", "r", "--resume")
    assert result.json["reason"] == "not-next"
    result = run_phase(m, root, "001-alpha", "plan", "opus", "r", "--fresh")
    assert result.json["reason"] == "not-next"
    assert not state_file(root).exists()
    assert {k: v for k, v in tree_snapshot(root).items() if not k.startswith(".specify/sdd-drive")} == before


def test_run_refuses_a_dirty_tree_and_keeps_it(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_tree(root, {"mine.txt": "my work\n"})
    result = run_phase(m, root, "001-alpha", "plan")
    assert (result.code, result.json["reason"], result.json["dirty"]) == (1, "dirty", ["mine.txt"])
    assert (root / "mine.txt").read_text(encoding="utf-8") == "my work\n"
    assert not state_file(root).exists()


def test_run_branch_diverged(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    start = branch_of(root)
    git_run(root, "switch", "--quiet", "-c", "001-alpha")
    write_tree(root, {"other.txt": "x"})
    commit_all(root)
    git_run(root, "switch", "--quiet", start)
    write_tree(root, {"mine.txt": "x"})
    commit_all(root)
    result = run_phase(m, root, "001-alpha", "plan")
    assert (result.code, result.json["reason"]) == (1, "branch-diverged")
    assert branch_of(root) == start and not state_file(root).exists()


def test_run_success_prepares_and_records(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_tree(root, {".specify/feature.json": '{"feature_directory": "specs/000-x", "keep": true}',
                      ".specify/sdd-drive/.gitignore": OWN_GITIGNORE.decode(), ".specify/sdd-drive/cancel": ""})
    start_head = head_of(root)
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    result = run_phase(m, root, "001-alpha", "plan", "opus", "Design work with new mechanisms.")
    assert result.code == 0, result.describe()
    assert json.loads((root / ".specify/feature.json").read_text(encoding="utf-8")) == {
        "feature_directory": "specs/001-alpha", "keep": True}
    assert not (root / ".specify/sdd-drive/cancel").exists()
    assert branch_of(root) == "001-alpha"
    state = read_state(root)
    record = state["attempts"][0]
    assert (record["id"], record["model"], record["reason"], record["auto"], record["resume"]) == (
        1, "opus", "Design work with new mechanisms.", False, False)
    assert state["launch"] is None and state["driver"] is None
    # run itself never commits or pushes: the only new commit is the fake child's.
    log = git_run(root, "log", "--format=%s", f"{start_head}..HEAD").splitlines()
    assert log == ["fake plan for 001-alpha"]


def test_run_writes_a_pending_attempt_and_launch_before_the_driver(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    monkeypatch.setattr(m, "start_driver", lambda root, token: True)
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(dict(TIMING, watch_seconds=0.2)))
    result = run_phase(m, root, "001-alpha", "plan")
    assert result.code == 0 and result.watched["status"] == "running"
    state = read_state(root)
    assert state["attempts"][0]["outcome"] is None and state["launch"]["token"]
    assert status(m, root)["next"]["action"] == "wait"


def test_run_start_failure_is_launch_failed(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    monkeypatch.setattr(m, "start_driver", lambda root, token: False)
    result = run_phase(m, root, "001-alpha", "plan")
    assert result.code == 0, result.describe()
    data = result.watched
    assert data["status"] == "finished" and data["attempts"][0]["outcome"] == "launch-failed"
    assert data["attempts"][0]["detail"]["code"] == "launch"
    assert read_state(root)["launch"] is None
    assert data["failures"] == {}


# ======================================================== T017 driver success and watch


def test_child_receives_the_documented_arguments_and_the_brief(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    expected_brief = drive(m, root, "brief", "--spec", "001-alpha", "--phase", "plan").text
    result = run_phase(m, root, "001-alpha", "plan", "opus", "Design.")
    assert result.watched["status"] == "finished", result.describe()
    call = calls(tmp_path)[0]
    session = read_state(root)["attempts"][0]["session_id"]
    assert call["argv"][:12] == ["-p", "--output-format", "stream-json", "--verbose", "--model", "opus",
                                 "--session-id", session, "--json-schema", json.dumps(m.REPORT_SCHEMA, separators=(",", ":")),
                                 "--permission-mode", "acceptEdits"]
    assert call["argv"][12:] == ["--permission-prompts", "none", "--allowedTools", "Bash", "Skill",
                                 "--disallowedTools", "AskUserQuestion", "Bash(git push*)"]
    assert call["stdin"] == expected_brief
    assert Path(call["cwd"]).resolve() == root.resolve()
    assert result.watched["attempts"][0]["model_used"] == ["claude-opus-test"]


def test_three_phases_succeed_and_record_worktree_and_task_ids(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD, "tasks": 4})
    for phase, after in (("plan", "planned"), ("tasks", "tasked"), ("implement", "implementing")):
        result = run_phase(m, root, "001-alpha", phase)
        data = result.watched
        assert data["status"] == "finished"
        assert data["attempts"][0]["outcome"] == "succeeded", data
        assert data["state_after"]["state"] == after
    state = read_state(root)
    assert [a["worktree"] is not None for a in state["attempts"]] == [True, True, True]
    assert state["attempts"][1]["task_ids"] == ["T001", "T002", "T003", "T004"]
    assert state["attempts"][0]["task_ids"] is None
    assert status(m, root)["next"]["action"] == "test"


@pytest.mark.parametrize("phase,action,code", [("plan", "plan-template", "plan-missing"),
                                               ("tasks", "tasks-template", "tasks-missing")])
def test_template_artifacts_are_verify_failed(m, tmp_path, monkeypatch, phase, action, code):
    specs = {"001-alpha": {"plan": True} if phase == "tasks" else {}}
    root = make_project(tmp_path, specs=specs)
    scenarios(monkeypatch, {"do": [action]})
    data = run_phase(m, root, "001-alpha", phase).watched
    assert data["attempts"][0]["outcome"] == "verify-failed"
    assert data["attempts"][0]["detail"]["code"] == code
    assert data["attempts"][0]["counts_as_failure"] is True


def test_driver_clears_launch_writes_driver_and_clears_it(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD, "sleep": 1.5})
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(dict(TIMING, watch_seconds=0.3)))
    first = run_phase(m, root, "001-alpha", "plan")
    assert first.watched["status"] == "running"
    seen = wait_for(lambda: read_state(root)["driver"])
    assert seen["phase"] == "running" and seen["attempt"] == 1 and read_state(root)["launch"] is None
    data = status(m, root)
    assert data["running"] is True and data["driver"]["phase"] == "running"
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(TIMING))
    final = drive(m, root, "watch")
    assert final.watched["status"] == "finished" and final.watched["attempts"][0]["outcome"] == "succeeded"
    assert read_state(root)["driver"] is None
    # the driver did not start the next phase by itself
    assert len(calls(tmp_path)) == 1


def test_watch_output_fields(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD,
                            "result": {"permission_denials": [{"tool_name": "WebFetch", "tool_input": {"url": "x"}},
                                                              {"tool_name": "WebFetch", "tool_input": {}}]}})
    run_phase(m, root, "001-alpha", "plan", "opus", "Design.")
    data = drive(m, root, "watch").watched
    assert list(data) == ["status", "attempts", "waiting_until", "state_after", "failures"]
    view = data["attempts"][0]
    assert list(view) == ["spec", "phase", "outcome", "auto", "counts_as_failure", "model", "model_used", "reason",
                          "session_id", "resume", "resume_failed", "duration_seconds", "summary", "failure", "detail",
                          "limit", "convergence", "findings", "findings_total", "auto_resume", "permission_denials"]
    assert view["permission_denials"] == ["WebFetch"]
    assert isinstance(view["duration_seconds"], int) and view["reason"] == "Design."
    assert data["state_after"] == {"state": "planned", "next_phase": "tasks", "tasks_total": 0, "tasks_open": 0}


def test_watch_without_any_attempt_is_no_driver(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    result = drive(m, root, "watch")
    assert (result.code, result.json["reason"]) == (1, "no-driver")


def test_watch_reports_the_last_finished_attempt(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    write_state(root, blank_state(attempts=[attempt(1)]))
    data = drive(m, root, "watch").watched
    assert data["status"] == "finished" and data["attempts"][0]["outcome"] == "succeeded"


def test_watch_driver_disappeared_finishes_with_null_outcome(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    driver = {"token": UUID1, "pid": 2147483646, "phase": "running", "attempt": 1, "waiting_until": None,
              "started_at": T0}
    write_state(root, blank_state(attempts=[attempt(1, phase="tasks", outcome=None)], driver=driver))
    data = drive(m, root, "watch").watched
    assert data["status"] == "finished"
    assert data["attempts"][-1]["outcome"] is None
    assert status(m, root)["next"]["action"] == "finalize"


def test_watch_minutes_range(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True}})
    write_state(root, blank_state(attempts=[attempt(1)]))
    assert drive(m, root, "watch", "--minutes", "1").code == 0
    assert drive(m, root, "watch", "--minutes", "115").code == 0


def test_two_specs_in_order(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}, "002-beta": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    order = []
    for _ in range(12):
        nxt = status(m, root)["next"]
        if nxt["action"] == "none":
            break
        order.append((nxt["spec"], nxt["phase"]))
        if nxt["action"] == "test":
            assert drive(m, root, "test", "--spec", nxt["spec"]).json["passed"] is True
        else:
            data = run_phase(m, root, nxt["spec"], nxt["phase"]).watched
            assert data["attempts"][-1]["outcome"] == "succeeded", data
    assert order == [("001-alpha", p) for p in ("plan", "tasks", "implement", "test", "check")] + \
                    [("002-beta", p) for p in ("plan", "tasks", "implement", "test", "check")]
    assert branch_of(root) == "002-beta"
    assert git_run(root, "merge-base", "--is-ancestor", "001-alpha", "002-beta") == ""


# ======================================================== T026 test


def ready_for_test(tmp_path, name="proj", command=PASS_CMD, extra_specs=None, baseline=True):
    specs = {"001-alpha": {"plan": True, "tasks": (2, 2), "command": command}}
    specs.update(extra_specs or {})
    root = make_project(tmp_path, name, specs=specs)
    if not baseline:
        write_state(root, blank_state())
    return root


def test_test_must_be_the_next_test(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 1)}})
    result = drive(m, root, "test", "--spec", "001-alpha")
    assert (result.code, result.json["reason"]) == (1, "not-next")
    assert not state_file(root).exists()


def test_test_refuses_dirty_running_and_pending(m, tmp_path):
    root = ready_for_test(tmp_path)
    write_tree(root, {"mine.txt": "x"})
    assert drive(m, root, "test", "--spec", "001-alpha").json["reason"] == "dirty"
    (root / "mine.txt").unlink()
    write_state(root, blank_state(baseline=["001-alpha"], attempts=[attempt(1, outcome=None)]))
    assert drive(m, root, "test", "--spec", "001-alpha").json["reason"] == "pending-finalize"
    write_state(root, blank_state(baseline=["001-alpha"]))
    with hold_lock(root):
        assert drive(m, root, "test", "--spec", "001-alpha").json["reason"] == "running"


@pytest.mark.parametrize("plan", ["# Plan: a\n\n**Testing**: pytest\n", "# Plan: a\n\n**Testing**: `N/A`\n",
                                  "# Plan: a\n\n**Testing**: `none`\n", "# Plan: a\n\n**Testing**: `TBD`\n",
                                  "# Plan: a\n\nno line\n", "# Plan: a\n\n**Testing**: `run --token=SECRETVALUE`\n"])
def test_no_test_command(m, tmp_path, plan):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": plan, "tasks": (1, 1)}})
    result = drive(m, root, "test", "--spec", "001-alpha")
    assert (result.code, result.json["reason"]) == (1, "no-test-command")
    assert "SECRETVALUE" not in result.text
    assert "detail" in result.json
    assert not state_file(root).exists() or read_state(root)["tests"] == []


def test_test_runs_in_the_root_with_empty_stdin(m, tmp_path):
    script = 'import os, sys; open("seen.txt", "w").write(os.getcwd() + "|" + sys.stdin.read())'
    command = f'"{PY}" -c "{script}"'.replace('"seen.txt"', "'seen.txt'").replace('"w"', "'w'").replace('"|"', "'|'")
    root = ready_for_test(tmp_path, command=command)
    write_tree(root, {".gitignore": "seen.txt\n"})
    commit_all(root)
    result = drive(m, root, "test", "--spec", "001-alpha")
    assert result.json["passed"] is True, result.json
    cwd, _, stdin = (root / "seen.txt").read_text().partition("|")
    assert Path(cwd).resolve() == root.resolve() and stdin == ""


def test_passing_test_records_every_covered_spec(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)},
                                         "002-beta": {"plan": True, "tasks": (1, 1)},
                                         "003-gamma": {"plan": True, "tasks": (1, 1), "command": FAIL_CMD},
                                         "004-delta": {"plan": True, "tasks": (1, 1)}})
    nxt = status(m, root)["next"]
    assert nxt["covers"] == ["001-alpha", "002-beta"] and nxt["test_command"] == PASS_CMD
    result = drive(m, root, "test", "--spec", "001-alpha").json
    assert list(result) == ["spec", "command", "exit_code", "passed", "covers", "duration_seconds", "output_tail"]
    assert result["covers"] == ["001-alpha", "002-beta"] and result["passed"] is True
    tests = read_state(root)["tests"]
    assert [t["spec"] for t in tests] == ["001-alpha", "002-beta"]
    assert all(t["exit_code"] == 0 and t["head"] == head_of(root) for t in tests)
    assert list(tests[0]) == ["spec", "tasks_hash", "command", "exit_code", "head", "at"]
    assert status(m, root)["next"]["spec"] == "003-gamma"


def test_failing_test_records_only_the_spec_and_counts(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1), "command": FAIL_CMD},
                                         "002-beta": {"plan": True, "tasks": (1, 1), "command": FAIL_CMD}})
    result = drive(m, root, "test", "--spec", "001-alpha").json
    assert (result["passed"], result["exit_code"], result["covers"]) == (False, 3, ["001-alpha"])
    assert result["output_tail"] == ["boom"]
    assert [t["spec"] for t in read_state(root)["tests"]] == ["001-alpha"]
    row = status(m, root)["specs"][0]
    assert (row["state"], row["next_phase"], row["failures"]) == ("failed", "test", {"test": 1})
    assert status(m, root)["next"]["spec"] == "001-alpha"


def test_output_tail_is_the_last_40_lines_with_secret_lines_hidden(m, tmp_path):
    # The secret is assembled at run time so that the command itself does not look like a secret.
    script = ("[print('line', i) for i in range(60)]; print('key tok' + 'en=' + 'gh' + 'p_' + 'a' * 30); "
              "print('end')")
    root = ready_for_test(tmp_path, command=f'"{PY}" -c "{script}"')
    before = tree_snapshot(root)
    result = drive(m, root, "test", "--spec", "001-alpha").json
    assert len(result["output_tail"]) == 40
    assert result["output_tail"][-2:] == ["(line not shown: looks like a secret)", "end"]
    assert result["output_tail"][0] == "line 22"
    assert SECRET_VALUE not in state_file(root).read_text(encoding="utf-8")
    after = {k: v for k, v in tree_snapshot(root).items() if not k.startswith(".specify/sdd-drive")}
    assert after == before


def test_non_git_test_records_null_head(m, tmp_path):
    root = make_project(tmp_path, git=False, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}})
    assert drive(m, root, "test", "--spec", "001-alpha").json["passed"] is True
    assert read_state(root)["tests"][0]["head"] is None


# ======================================================== T027 completion and the existing baseline


def checked_spec(tmp_path, baseline=(), **state_changes):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 2)}, "002-beta": {}})
    write_state(root, blank_state(baseline=baseline, **state_changes))
    return root


def first_row(m, root):
    return status(m, root)["specs"][0]


def test_unchecked_tasks_keep_next_on_the_spec(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 1)}, "002-beta": {}})
    data = status(m, root)
    assert (data["specs"][0]["state"], data["specs"][0]["next_phase"]) == ("implementing", "implement")
    assert data["next"]["spec"] == "001-alpha"


def test_all_checked_without_test_record_needs_test(m, tmp_path):
    root = checked_spec(tmp_path)
    assert (first_row(m, root)["state"], first_row(m, root)["next_phase"]) == ("implementing", "test")
    assert status(m, root)["next"]["action"] == "test"


def test_passed_test_at_current_hash_and_head_needs_check(m, tmp_path):
    root = checked_spec(tmp_path)
    write_state(root, blank_state(tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"), head=head_of(root))]))
    row = first_row(m, root)
    assert (row["state"], row["next_phase"]) == ("implementing", "check")
    nxt = status(m, root)["next"]
    assert (nxt["action"], nxt["phase"], nxt["hints"]["check_failures"]) == ("run", "check", 0)


def test_new_commit_after_the_test_needs_a_new_test(m, tmp_path):
    root = checked_spec(tmp_path)
    write_state(root, blank_state(tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"), head=head_of(root))]))
    write_tree(root, {"src/new.py": "x"})
    commit_all(root)
    assert first_row(m, root)["next_phase"] == "test"


def test_non_git_compares_only_the_tasks_hash(m, tmp_path):
    root = make_project(tmp_path, git=False, specs={"001-alpha": {"plan": True, "tasks": (2, 2)}})
    write_state(root, blank_state(tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"))]))
    assert first_row(m, root)["next_phase"] == "check"


def test_converged_check_at_current_hash_is_done(m, tmp_path):
    root = checked_spec(tmp_path)
    current = hash_of(m, root, "001-alpha")
    write_state(root, blank_state(attempts=[attempt(1, phase="check", convergence="converged", tasks_hash=current)]))
    assert first_row(m, root)["state"] == "done"
    assert status(m, root)["next"]["spec"] == "002-beta"


def test_changed_tasks_invalidate_old_test_and_check_records(m, tmp_path):
    root = checked_spec(tmp_path)
    current = hash_of(m, root, "001-alpha")
    write_state(root, blank_state(attempts=[attempt(1, phase="check", convergence="converged", tasks_hash=current)],
                                  tests=[test_record("001-alpha", current, head=head_of(root))]))
    add_spec(root, "001-alpha", plan=True, tasks=tasks_text("001-alpha", 2, 2) + "\nNotes changed.\n")
    commit_all(root)
    assert first_row(m, root)["next_phase"] == "test"


def test_failed_last_test_is_failed_state(m, tmp_path):
    root = checked_spec(tmp_path)
    current = hash_of(m, root, "001-alpha")
    write_state(root, blank_state(tests=[test_record("001-alpha", current, exit_code=1, head=head_of(root))]))
    row = first_row(m, root)
    assert (row["state"], row["next_phase"], row["failures"]) == ("failed", "test", {"test": 1})


def test_baseline_needs_only_a_test_at_the_current_hash(m, tmp_path):
    root = checked_spec(tmp_path, baseline=["001-alpha"])
    row = first_row(m, root)
    assert (row["state"], row["next_phase"], row["baseline"]) == ("implementing", "test", True)
    old_head = "0" * 40
    write_state(root, blank_state(baseline=["001-alpha"],
                                  tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"), head=old_head)]))
    row = first_row(m, root)
    assert (row["state"], row["next_phase"]) == ("done", None)


def test_baseline_never_has_next_phase_check(m, tmp_path):
    root = checked_spec(tmp_path, baseline=["001-alpha"])
    for record in ([], [test_record("001-alpha", hash_of(m, root, "001-alpha"), head=head_of(root))]):
        write_state(root, blank_state(baseline=["001-alpha"], tests=record))
        assert first_row(m, root)["next_phase"] != "check"


def test_baseline_with_an_implement_attempt_follows_the_normal_rules(m, tmp_path):
    root = checked_spec(tmp_path, baseline=["001-alpha"])
    write_state(root, blank_state(baseline=["001-alpha"], attempts=[attempt(1, phase="implement")],
                                  tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"), head=head_of(root))]))
    row = first_row(m, root)
    assert (row["baseline"], row["next_phase"]) == (False, "check")


def test_after_clear_there_is_no_baseline(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 2)}})
    assert first_row(m, root)["baseline"] is True
    assert drive(m, root, "clear").json == {"cleared": True, "baseline_reset": True}
    state = read_state(root)
    assert (state["baseline"], state["baseline_reset"]) == ([], True)
    assert first_row(m, root)["baseline"] is False
    assert drive(m, root, "test", "--spec", "001-alpha").json["passed"] is True
    assert first_row(m, root)["next_phase"] == "check"


def test_first_status_matches_the_written_baseline(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)},
                                         "002-beta": {"plan": True, "tasks": (1, 1)},
                                         "003-gamma": {"plan": True, "tasks": (1, 0)}})
    before = [r["baseline"] for r in status(m, root)["specs"]]
    assert drive(m, root, "test", "--spec", "001-alpha").json["covers"] == ["001-alpha", "002-beta"]
    assert read_state(root)["baseline"] == ["001-alpha", "002-beta"]
    assert [r["baseline"] for r in status(m, root)["specs"]] == before == [True, True, False]
    assert [r["state"] for r in status(m, root)["specs"]] == ["done", "done", "tasked"]


# ======================================================== T028 check


def ready_for_check(m, tmp_path, monkeypatch, *, remote=False):
    """001 implemented by this skill (implement attempt), tested at the current HEAD; next is check."""
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (3, 3)}, "002-beta": {}})
    git_run(root, "switch", "--quiet", "-c", "001-alpha")
    if remote:
        bare_remote(tmp_path, root)
    write_state(root, blank_state(attempts=[attempt(1, phase="implement", task_ids=["T001", "T002", "T003"])],
                                  tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"), head=head_of(root))]))
    assert status(m, root)["next"]["phase"] == "check"
    return root


def run_check(m, root, monkeypatch, scenario):
    scenarios(monkeypatch, scenario)
    result = run_phase(m, root, "001-alpha", "check", "opus", "Careful comparison.")
    return result.watched


def test_check_converged_is_done_at_once(m, tmp_path, monkeypatch):
    root = ready_for_check(m, tmp_path, monkeypatch)
    start = head_of(root)
    data = run_check(m, root, monkeypatch, {"report": {"status": "completed", "summary": "Converged",
                                                       "convergence": "converged"}})
    view = data["attempts"][0]
    assert (view["outcome"], view["convergence"], view["findings"]) == ("succeeded", "converged", None)
    assert head_of(root) == start
    assert data["state_after"]["state"] == "done"
    nxt = status(m, root)["next"]
    assert (nxt["spec"], nxt["phase"]) == ("002-beta", "plan")
    assert read_state(root)["attempts"][-1]["tasks_hash"] == hash_of(m, root, "001-alpha")


def test_check_said_appended_but_nothing_changed(m, tmp_path, monkeypatch):
    root = ready_for_check(m, tmp_path, monkeypatch)
    data = run_check(m, root, monkeypatch, {"report": {"status": "completed", "summary": "x",
                                                       "convergence": "tasks-appended"}})
    view = data["attempts"][0]
    assert (view["outcome"], view["detail"]["code"]) == ("verify-failed", "check-no-tasks")
    assert status(m, root)["specs"][0]["state"] == "failed"


def test_check_gaps_found(m, tmp_path, monkeypatch):
    root = ready_for_check(m, tmp_path, monkeypatch)
    data = run_check(m, root, monkeypatch, {"do": ["append"], "commit_only": ["specs/001-alpha/tasks.md"],
                                            "report": {"status": "completed", "summary": "x",
                                                       "convergence": "tasks-appended"}})
    view = data["attempts"][0]
    assert (view["outcome"], view["convergence"], view["counts_as_failure"]) == ("gaps-found", "tasks-appended", True)
    assert view["detail"] is None
    assert view["findings"] == [
        {"id": "T004", "text": "Implement the missing retry", "source_ref": "FR-008", "gap_type": "missing"},
        {"id": "T005", "text": "Remove the unrequested cache", "source_ref": "plan.md", "gap_type": "unrequested"},
    ]
    assert view["findings_total"] == 2
    record = read_state(root)["attempts"][-1]
    assert record["appended"] == ["T004", "T005"]
    assert record["task_ids"] == ["T001", "T002", "T003", "T004", "T005"]
    assert data["failures"] == {"check": 1}
    row = status(m, root)["specs"][0]
    assert (row["state"], row["next_phase"]) == ("implementing", "implement")
    assert status(m, root)["next"]["spec"] == "001-alpha"


def test_check_said_converged_but_appended_is_report_mismatch(m, tmp_path, monkeypatch):
    root = ready_for_check(m, tmp_path, monkeypatch)
    data = run_check(m, root, monkeypatch, {"do": ["append"], "commit_only": ["specs/001-alpha/tasks.md"],
                                            "report": {"status": "completed", "summary": "x",
                                                       "convergence": "converged"}})
    view = data["attempts"][0]
    assert (view["outcome"], view["detail"]["code"]) == ("gaps-found", "report-mismatch")


@pytest.mark.parametrize("scenario,code,paths", [
    ({"do": ["rewrite-tasks"]}, "check-rewrote-tasks", ["specs/001-alpha/tasks.md"]),
    ({"do": ["append-bad"]}, "check-rewrote-tasks", ["specs/001-alpha/tasks.md"]),
    ({"do": ["touch-code"]}, "check-touched-files", ["src/extra.py"]),
    ({"do": ["touch-plan"]}, "check-touched-files", ["specs/001-alpha/plan.md"]),
    ({"do": ["touch-spec"]}, "protected-changed", ["specs/001-alpha/spec.md"]),
    ({"do": ["touch-constitution"]}, "protected-changed", [".specify/memory/constitution.md"]),
    ({"do": ["append"], "commit": False}, "uncommitted", ["specs/001-alpha/tasks.md"]),
])
def test_check_verify_failures_are_not_reverted(m, tmp_path, monkeypatch, scenario, code, paths):
    root = ready_for_check(m, tmp_path, monkeypatch)
    data = run_check(m, root, monkeypatch, dict(scenario, report={"status": "completed", "summary": "x"}))
    view = data["attempts"][0]
    assert (view["outcome"], view["detail"]["code"]) == ("verify-failed", code), view
    if paths is not None:
        assert view["detail"]["paths"] == paths
    assert view["findings"] is None
    if scenario.get("commit") is False:
        assert "specs/001-alpha/tasks.md" in git_run(root, "status", "--porcelain")


def test_check_rewrite_with_checked_task_is_detected(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (3, 3)}})
    git_run(root, "switch", "--quiet", "-c", "001-alpha")
    text = tasks_text("001-alpha", 3, 3) + "\n- [ ] T004 already open\n"
    add_spec(root, "001-alpha", plan=True, tasks=text.replace("- [ ] T004 already open", "- [x] T004 already open"))
    commit_all(root)
    write_state(root, blank_state(attempts=[attempt(1, phase="implement")],
                                  tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"), head=head_of(root))]))
    path = root / "specs/001-alpha/tasks.md"
    scenarios(monkeypatch, {"do": [], "files": {"specs/001-alpha/tasks.md": path.read_text().replace("- [x] T001", "- [ ] T001")},
                            "report": {"status": "completed", "summary": "x"}})
    view = run_phase(m, root, "001-alpha", "check", "opus", "r").watched["attempts"][0]
    assert view["detail"]["code"] == "check-rewrote-tasks"


def test_check_push_is_pushed(m, tmp_path, monkeypatch):
    root = ready_for_check(m, tmp_path, monkeypatch, remote=True)
    data = run_check(m, root, monkeypatch, {"do": ["append", "push"], "commit_only": ["specs/001-alpha/tasks.md"],
                                            "report": {"status": "completed", "summary": "x"}})
    assert data["attempts"][0]["detail"]["code"] == "pushed"


def test_gaps_found_then_implement_test_check_again_without_looping(m, tmp_path, monkeypatch):
    root = ready_for_check(m, tmp_path, monkeypatch)
    run_check(m, root, monkeypatch, {"do": ["append"], "commit_only": ["specs/001-alpha/tasks.md"]})
    scenarios(monkeypatch, {})
    assert run_phase(m, root, "001-alpha", "implement").watched["attempts"][0]["outcome"] == "succeeded"
    assert len(calls(tmp_path)) == 2  # nothing ran on its own after gaps-found
    nxt = status(m, root)["next"]
    assert (nxt["action"], nxt["spec"]) == ("test", "001-alpha")
    assert drive(m, root, "test", "--spec", "001-alpha").json["passed"] is True
    nxt = status(m, root)["next"]
    assert (nxt["phase"], nxt["hints"]["check_failures"]) == ("check", 1)
    data = run_check(m, root, monkeypatch, {"report": {"status": "completed", "summary": "Converged",
                                                       "convergence": "converged"}})
    assert data["state_after"]["state"] == "done"


def test_findings_are_capped_cleaned_and_parsed(m, tmp_path, monkeypatch):
    root = ready_for_check(m, tmp_path, monkeypatch)
    path = root / "specs/001-alpha/tasks.md"
    lines = ["", "## Phase 2: Convergence", ""]
    lines.append(f"- [ ] T004 Store the key {SECRET_VALUE} per FR-001 (missing)")
    lines.append("- [ ] T005 " + "Long " * 100 + "per FR-002 (partial)")
    lines.append("- [ ] T006 No reference here")
    lines += [f"- [ ] T{n:03d} Item {n} per FR-003 (contradicts)" for n in range(7, 70)]
    text = path.read_text(encoding="utf-8") + "\n".join(lines) + "\n"
    data = run_check(m, root, monkeypatch, {"do": [], "files": {"specs/001-alpha/tasks.md": text},
                                            "commit_only": ["specs/001-alpha/tasks.md"]})
    view = data["attempts"][0]
    assert view["outcome"] == "gaps-found"
    assert view["findings_total"] == 66 and len(view["findings"]) == 50
    assert view["findings"][0]["text"] == SECRET_TEXT
    assert len(view["findings"][1]["text"]) <= 300
    assert view["findings"][2] == {"id": "T006", "text": "No reference here", "source_ref": None, "gap_type": None}
    assert SECRET_VALUE not in json.dumps(data)


def test_baseline_never_gets_a_check_session(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (2, 2)}, "002-beta": {}})
    assert drive(m, root, "test", "--spec", "001-alpha").json["passed"] is True
    nxt = status(m, root)["next"]
    assert (nxt["spec"], nxt["phase"]) == ("002-beta", "plan")
    assert run_phase(m, root, "001-alpha", "check", "opus", "r").json["reason"] == "not-next"
    assert calls(tmp_path) == []


# ======================================================== T035 failures and verification


@pytest.mark.parametrize("kind", ["requirements", "blocked-task", "tests", "tooling", "other"])
def test_failed_report_is_recorded_and_counted(m, tmp_path, monkeypatch, kind):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (3, 1)}, "002-beta": {}})
    report = {"status": "failed", "summary": "could not", "tasks": ["T003"] if kind == "blocked-task" else [],
              "failure": {"kind": kind, "step": "T002", "reason": "needs a push"}}
    scenarios(monkeypatch, {"do": [], "report": report})
    result = run_phase(m, root, "001-alpha", "implement")
    assert result.code == 0, result.describe()
    view = result.watched["attempts"][0]
    assert (view["outcome"], view["counts_as_failure"]) == ("failed", True)
    assert view["failure"] == {"kind": kind, "step": "T002", "reason": "needs a push",
                               "tasks": ["T003"] if kind == "blocked-task" else []}
    data = status(m, root)
    assert (data["specs"][0]["state"], data["specs"][0]["next_phase"], data["specs"][0]["failures"]) == (
        "failed", "implement", {"implement": 1})
    assert (data["next"]["spec"], data["next"]["phase"], data["next"]["action"]) == ("001-alpha", "implement", "run")


def implementing(tmp_path, remote=False, tasks=(3, 0)):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": tasks}})
    git_run(root, "switch", "--quiet", "-c", "001-alpha")
    if remote:
        bare_remote(tmp_path, root)
    write_state(root, blank_state(attempts=[attempt(1, phase="tasks", task_ids=["T001", "T002", "T003"])]))
    return root


@pytest.mark.parametrize("scenario,code,paths", [
    ({"do": ["implement-partial"]}, "tasks-unfinished", []),
    ({"do": ["implement", "remove-task"]}, "tasks-removed", ["specs/001-alpha/tasks.md"]),
    ({"do": ["implement", "touch-spec"]}, "protected-changed", ["specs/001-alpha/spec.md"]),
    ({"do": ["implement", "touch-constitution"]}, "protected-changed", [".specify/memory/constitution.md"]),
    ({"do": ["implement", "touch-template"]}, "protected-changed", [".specify/templates/plan-template.md"]),
    ({"do": ["implement", "dirty"], "commit_only": ["specs/001-alpha/tasks.md", "src"]}, "uncommitted",
     ["left-behind.txt"]),
])
def test_verify_failed_codes(m, tmp_path, monkeypatch, scenario, code, paths):
    root = implementing(tmp_path)
    scenarios(monkeypatch, scenario)
    view = run_phase(m, root, "001-alpha", "implement").watched["attempts"][0]
    assert (view["outcome"], view["detail"]["code"], view["detail"]["paths"]) == ("verify-failed", code, paths)
    if code == "uncommitted":
        assert (root / "left-behind.txt").read_text() == "not committed\n"
        assert "left-behind.txt" in git_run(root, "status", "--porcelain")
    if code == "protected-changed":
        assert "Changed." in (root / paths[0]).read_text()
    row = status(m, root)["specs"][0]
    assert row["failures"] == {"implement": 1}
    if code == "tasks-unfinished":
        # Still on the implement phase: the failure is laid over it (data-model "失敗的疊加").
        assert (row["state"], row["next_phase"]) == ("failed", "implement")


def test_push_is_verify_failed(m, tmp_path, monkeypatch):
    root = implementing(tmp_path, remote=True)
    scenarios(monkeypatch, {"do": ["implement", "push"]})
    view = run_phase(m, root, "001-alpha", "implement").watched["attempts"][0]
    assert view["detail"]["code"] == "pushed"


def test_second_spec_failing_never_starts_the_third(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}, "002-beta": {},
                                         "003-gamma": {}})
    assert drive(m, root, "test", "--spec", "001-alpha").json["passed"] is True
    scenarios(monkeypatch, {"do": [], "report": {"status": "failed", "summary": "x",
                                                 "failure": {"kind": "requirements", "step": "plan", "reason": "conflict"}}})
    assert run_phase(m, root, "002-beta", "plan").watched["attempts"][0]["outcome"] == "failed"
    for _ in range(2):
        nxt = status(m, root)["next"]
        assert (nxt["spec"], nxt["phase"]) == ("002-beta", "plan")
    assert run_phase(m, root, "003-gamma", "plan").json["reason"] == "not-next"
    assert all("specs/003-gamma" not in c["stdin"] for c in calls(tmp_path))


def test_retry_after_a_failure_starts_from_the_failed_phase(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"do": [], "report": {"status": "failed", "summary": "x",
                                                 "failure": {"kind": "other", "step": "s", "reason": "r"}}},
              {"test_command": PASS_CMD})
    run_phase(m, root, "001-alpha", "plan")
    data = run_phase(m, root, "001-alpha", "plan").watched
    assert data["attempts"][0]["outcome"] == "succeeded"
    assert data["failures"] == {"plan": 1}
    assert status(m, root)["specs"][0]["state"] == "planned"


def test_permission_denials_are_tool_names_only(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD, "result": {"permission_denials": [
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}}, {"tool_name": "Bash", "tool_input": {}},
        {"tool_name": "WebFetch", "tool_input": {"url": "u"}}]}})
    data = run_phase(m, root, "001-alpha", "plan").watched
    assert data["attempts"][0]["permission_denials"] == ["Bash", "WebFetch"]
    assert "rm -rf" not in state_file(root).read_text(encoding="utf-8")


# ======================================================== T036 non-failures and finalize


@pytest.mark.parametrize("scenario,outcome,code", [
    ({"do": [], "result": {"is_error": True, "api_error_status": 401, "result": "Invalid API key"}}, "api-error", "api-error"),
    ({"do": [], "result": {"is_error": True, "api_error_status": 404, "result": "model not found"}}, "api-error", "api-error"),
    ({"do": [], "result": {"is_error": True, "subtype": "error_max_turns", "result": None}}, "api-error", "api-error"),
    ({"do": [], "no_result": True}, "interrupted", "no-result"),
    ({"do": [], "report": None}, "interrupted", "no-report"),
    ({"do": [], "report": {"status": "completed"}}, "interrupted", "no-report"),
])
def test_non_failure_endings_are_not_counted(m, tmp_path, monkeypatch, scenario, outcome, code):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, scenario)
    data = run_phase(m, root, "001-alpha", "plan").watched
    view = data["attempts"][0]
    assert (view["outcome"], view["detail"]["code"], view["counts_as_failure"]) == (outcome, code, False)
    if code == "api-error":
        assert view["detail"]["text"] in ("Invalid API key", "model not found", "error_max_turns")
    assert data["failures"] == {}
    nxt = status(m, root)["next"]
    assert (nxt["action"], nxt["last_outcome"], nxt["session_id"]) == ("resume", outcome, view["session_id"])


def test_missing_claude_executable_is_launch_failed(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    monkeypatch.setenv("SDD_DRIVE_CLAUDE", json.dumps([str(tmp_path / "no-such-claude")]))
    data = run_phase(m, root, "001-alpha", "plan").watched
    view = data["attempts"][0]
    assert (view["outcome"], view["detail"]["code"], view["counts_as_failure"]) == ("launch-failed", "launch", False)
    assert status(m, root)["next"]["action"] == "run"


def pending(root, **changes):
    write_state(root, blank_state(attempts=[attempt(1, outcome=None, started_at=T0)], **changes))


def test_pending_attempt_needs_finalize(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    pending(root)
    data = status(m, root)
    assert data["pending_finalize"] is True
    assert (data["next"]["action"], data["next"]["spec"], data["next"]["phase"]) == ("finalize", "001-alpha", "plan")
    assert run_phase(m, root, "001-alpha", "plan").json["reason"] == "pending-finalize"


def test_stale_driver_record_needs_finalize(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state(attempts=[attempt(1)], driver={"token": UUID2, "pid": 99999, "phase": "running",
                                                                 "attempt": 1, "waiting_until": None, "started_at": T0}))
    assert status(m, root)["next"]["action"] == "finalize"


def test_finalize_records_interrupted_with_the_fingerprint(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    pending(root, launch={"token": UUID2, "at": T0})
    write_tree(root, {"half-done.txt": "x"})
    result = drive(m, root, "finalize")
    assert result.code == 0, result.describe()
    data = result.json
    assert list(data) == ["spec", "phase", "model", "started_at", "outcome", "auto_resume", "state_after"]
    assert (data["spec"], data["phase"], data["model"], data["started_at"], data["outcome"]) == (
        "001-alpha", "plan", "opus", T0, "interrupted")
    assert data["state_after"] == {"state": "not-started", "next_phase": "plan", "tasks_total": 0, "tasks_open": 0}
    state = read_state(root)
    record = state["attempts"][0]
    assert record["detail"]["code"] == "no-result" and record["worktree"] == m.worktree_fingerprint(root)
    assert state["launch"] is None and state["driver"] is None
    after = status(m, root)
    assert after["leftovers"] is True and after["next"]["action"] == "resume"
    assert after["specs"][0]["failures"] == {}


def test_finalize_nothing_running_and_idempotent(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state(attempts=[attempt(1)]))
    assert drive(m, root, "finalize").json["reason"] == "nothing-to-finalize"
    pending(root)
    with hold_lock(root):
        assert drive(m, root, "finalize").json["reason"] == "running"
    assert drive(m, root, "finalize").code == 0
    first = read_state(root)
    assert drive(m, root, "finalize").json["reason"] == "nothing-to-finalize"
    assert read_state(root) == first


def test_run_exit_code_is_zero_when_the_child_fails(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"do": [], "exit": 1, "report": {"status": "failed", "summary": "x",
                                                             "failure": {"kind": "other", "step": "s", "reason": "r"}}})
    assert run_phase(m, root, "001-alpha", "plan").code == 0


# ======================================================== T041 manual resume


def interrupted_plan(m, tmp_path, monkeypatch, scenario=None):
    root = make_project(tmp_path, specs={"001-alpha": {}, "002-beta": {}})
    scenarios(monkeypatch, scenario or {"do": [], "no_result": True})
    first = run_phase(m, root, "001-alpha", "plan", "opus", "Design.").watched["attempts"][0]
    assert first["outcome"] in ("interrupted", "usage-limit", "api-error")
    return root, first


def test_resume_is_next_after_an_interruption(m, tmp_path, monkeypatch):
    root, first = interrupted_plan(m, tmp_path, monkeypatch)
    nxt = status(m, root)["next"]
    assert (nxt["action"], nxt["session_id"], nxt["model"], nxt["last_outcome"]) == (
        "resume", first["session_id"], "opus", "interrupted")
    assert nxt["limit"] is None and nxt["auto_resume"] is None
    assert run_phase(m, root, "001-alpha", "plan", "opus", "r").json["reason"] == "not-next"


def test_run_resume_continues_the_same_session(m, tmp_path, monkeypatch):
    root, first = interrupted_plan(m, tmp_path, monkeypatch)
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    data = run_phase(m, root, "001-alpha", "plan", "opus", "Resuming the interrupted session.", "--resume").watched
    view = data["attempts"][0]
    assert (view["outcome"], view["resume"], view["session_id"], view["auto"]) == (
        "succeeded", True, first["session_id"], False)
    call = calls(tmp_path)[-1]
    assert call["argv"][6:8] == ["--resume", first["session_id"]] and "--session-id" not in call["argv"]
    assert "First check the current state of the files again" in call["stdin"]
    assert status(m, root)["next"]["phase"] == "tasks"


def test_resume_fresh_starts_a_new_session(m, tmp_path, monkeypatch):
    root, first = interrupted_plan(m, tmp_path, monkeypatch)
    scenarios(monkeypatch, {"test_command": PASS_CMD})
    data = run_phase(m, root, "001-alpha", "plan", "opus", "Fresh session.", "--resume", "--fresh").watched
    view = data["attempts"][0]
    assert view["session_id"] != first["session_id"] and view["resume"] is False
    call = calls(tmp_path)[-1]
    assert "--session-id" in call["argv"] and "--resume" not in call["argv"]
    assert "First check the current state of the files again" in call["stdin"]


def test_failed_resume_is_resume_failed_and_not_counted(m, tmp_path, monkeypatch):
    root, first = interrupted_plan(m, tmp_path, monkeypatch)
    scenarios(monkeypatch, {"fail_resume": True})
    data = run_phase(m, root, "001-alpha", "plan", "opus", "r", "--resume").watched
    view = data["attempts"][0]
    assert (view["resume_failed"], view["counts_as_failure"], view["outcome"]) == (True, False, "api-error")
    assert data["failures"] == {}
    assert status(m, root)["next"]["action"] == "resume"


def test_leftovers_allow_resume_and_changed_ones_do_not(m, tmp_path, monkeypatch):
    root, first = interrupted_plan(m, tmp_path, monkeypatch, {"do": [], "commit": False, "no_result": True,
                                                              "files": {"specs/001-alpha/research.md": "half\n"}})
    data = status(m, root)
    assert data["dirty"] == ["specs/001-alpha/research.md"] and data["leftovers"] is True
    write_tree(root, {"mine.txt": "x"})
    data = status(m, root)
    assert data["leftovers"] is False
    assert run_phase(m, root, "001-alpha", "plan", "opus", "r", "--resume").json["reason"] == "dirty"
    (root / "mine.txt").unlink()
    scenarios(monkeypatch, {"do": ["plan"], "test_command": PASS_CMD})
    data = run_phase(m, root, "001-alpha", "plan", "opus", "r", "--resume").watched
    assert data["attempts"][0]["outcome"] == "succeeded"
    assert git_run(root, "status", "--porcelain") == ""


def test_done_specs_are_not_redone_and_planned_goes_to_tasks(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}, "002-beta": {"plan": True},
                                         "003-gamma": {}})
    write_state(root, blank_state(baseline=["001-alpha"], tests=[test_record("001-alpha", hash_of(m, root, "001-alpha"))]))
    nxt = status(m, root)["next"]
    assert (nxt["spec"], nxt["phase"], nxt["action"]) == ("002-beta", "tasks", "run")


def test_resume_does_not_redo_checked_tasks(m, tmp_path, monkeypatch):
    root = implementing(tmp_path)
    scenarios(monkeypatch, {"do": ["implement-partial"], "no_result": True})
    run_phase(m, root, "001-alpha", "implement")
    assert status(m, root)["specs"][0]["tasks_open"] == 2
    scenarios(monkeypatch, {"do": ["implement"]})
    data = run_phase(m, root, "001-alpha", "implement", "sonnet", "r", "--resume").watched
    assert data["attempts"][0]["outcome"] == "succeeded"
    assert status(m, root)["specs"][0]["tasks_open"] == 0


# ======================================================== T042 usage limits


def window_event(reset: float | None, kind: str = "five_hour", status: str = "rejected", **extra) -> dict:
    window = {"utilization": 1.0, "status": status}
    if reset is not None:
        window["resetsAt"] = reset
    info = {"status": "rejected", "rateLimitType": kind, "overageStatus": "rejected",
            "unifiedWindows": {kind: window}}
    if reset is not None:
        info["resetsAt"] = reset
    info.update(extra)
    return {"type": "rate_limit_event", "rate_limit_info": info}


LIMIT_RESULT = {"is_error": True, "api_error_status": 429, "result": "You've hit your limit"}


def test_compute_limit_cases(m):
    start = "2026-11-21T10:00:00Z"
    reset = m.parse_ts("2026-11-21T15:10:00Z")
    later = m.parse_ts("2026-11-28T00:00:00Z")
    windows = {"status": "rejected", "rateLimitType": "five_hour", "overageStatus": "rejected",
               "unifiedWindows": {"five_hour": {"status": "rejected", "resetsAt": reset},
                                  "seven_day": {"status": "rejected", "resetsAt": later},
                                  "seven_day_opus": {"status": "allowed", "resetsAt": later + 99}}}
    assert m.compute_limit([windows], start) == {"waitable": True, "types": ["five_hour", "seven_day"],
                                                 "resets_at": "2026-11-28T00:00:00Z", "overage_status": "rejected"}
    assert m.compute_limit([{"status": "rejected", "rateLimitType": "overage", "overageStatus": "rejected"}], start) == {
        "waitable": False, "types": ["overage"], "resets_at": None, "overage_status": "rejected"}
    missing = {"status": "rejected", "rateLimitType": "five_hour", "unifiedWindows": {"five_hour": {"status": "rejected"}}}
    assert m.compute_limit([missing], start)["waitable"] is False
    assert m.compute_limit([], start) == {"waitable": False, "types": ["unknown"], "resets_at": None,
                                          "overage_status": None}
    spend = {"status": "rejected", "rateLimitType": "overage", "overageStatus": "rejected",
             "unifiedWindows": {"five_hour": {"status": "rejected", "resetsAt": reset}}}
    assert m.compute_limit([spend], start) == {"waitable": True, "types": ["five_hour", "overage"],
                                               "resets_at": "2026-11-21T15:10:00Z", "overage_status": "rejected"}
    simple = {"status": "rejected", "rateLimitType": "seven_day_sonnet", "resetsAt": reset}
    assert m.compute_limit([simple], start)["resets_at"] == "2026-11-21T15:10:00Z"
    assert m.compute_limit([dict(simple, dailyCapPaused=True)], start)["waitable"] is False
    assert m.compute_limit([dict(simple, resetsAt=m.parse_ts("2026-11-21T09:00:00Z"))], start)["waitable"] is False
    assert m.compute_limit([dict(simple, resetsAt="soon")], start)["waitable"] is False
    weird = {"status": "rejected", "rateLimitType": "monthly_thing", "overageStatus": "maybe"}
    assert m.compute_limit([weird], start) == {"waitable": False, "types": ["unknown"], "resets_at": None,
                                               "overage_status": None}


@pytest.mark.parametrize("result", [LIMIT_RESULT, {"is_error": True, "api_error_status": None,
                                                   "result": "Claude usage limit reached"},
                                    {"is_error": True, "api_error_status": 500, "result": "RATE LIMIT exceeded"}])
def test_usage_limit_is_detected_from_429_or_text(m, tmp_path, monkeypatch, result):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"do": [], "result": result})
    view = run_phase(m, root, "001-alpha", "plan").watched["attempts"][0]
    assert (view["outcome"], view["counts_as_failure"]) == ("usage-limit", False)
    assert view["limit"]["waitable"] is False and view["auto_resume"] == "not-waitable"


def test_only_overage_is_not_waitable_and_progress_is_kept(m, tmp_path, monkeypatch):
    root = implementing(tmp_path)
    overage = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "rateLimitType": "overage",
                                                               "overageStatus": "rejected", "resetsAt": 1}}
    scenarios(monkeypatch, {"do": ["implement-partial"], "commit": False, "events": [overage], "result": LIMIT_RESULT})
    data = run_phase(m, root, "001-alpha", "implement").watched
    view = data["attempts"][0]
    assert view["limit"] == {"waitable": False, "types": ["overage"], "resets_at": None, "overage_status": "rejected"}
    assert view["auto_resume"] == "not-waitable" and data["status"] == "finished"
    assert data["failures"] == {}
    assert "specs/001-alpha/tasks.md" in git_run(root, "status", "--porcelain")
    data = status(m, root)
    assert data["next"]["action"] == "resume" and data["leftovers"] is True
    assert data["next"]["limit"]["types"] == ["overage"] and data["next"]["auto_resume"] == "not-waitable"
    raw = state_file(root).read_text(encoding="utf-8")
    assert "unifiedWindows" not in raw and "rateLimitType" not in raw


def test_api_error_params_rate_limit_info_is_read(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    reset = int(time.time()) + 3600
    assistant = {"type": "assistant", "api_error": "usage_limit_reached",
                 "api_error_params": {"rate_limit_info": {"rateLimitType": "seven_day", "resetsAt": reset}},
                 "message": {"content": []}}
    scenarios(monkeypatch, {"do": [], "events": [assistant], "result": LIMIT_RESULT})
    first = run_phase(m, root, "001-alpha", "plan").watched
    assert first["status"] == "waiting"
    limit = first["attempts"][0]["limit"]
    assert (limit["waitable"], limit["types"]) == (True, ["seven_day"])
    drive(m, root, "cancel")
    assert drive(m, root, "watch").watched["attempts"][-1]["auto_resume"] == "cancelled"


# ======================================================== T043 automatic resume, cancel, driver survival


def limit_scenario(reset_in: float = 1.0, **extra) -> dict:
    return dict({"do": [], "events": [window_event(int(time.time() + reset_in))], "result": LIMIT_RESULT}, **extra)


def test_waitable_limit_waits_and_resumes_once(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, limit_scenario(2), {"test_command": PASS_CMD})
    first = run_phase(m, root, "001-alpha", "plan", "opus", "Design.").watched
    assert first["status"] == "waiting" and first["waiting_until"]
    view = first["attempts"][0]
    assert (view["outcome"], view["auto_resume"], view["limit"]["waitable"]) == ("usage-limit", "waiting", True)
    data = status(m, root)
    assert data["running"] is True and data["driver"]["phase"] == "waiting"
    assert data["driver"]["waiting_until"] == first["waiting_until"]
    assert data["running_attempt"]["limit"]["types"] == ["five_hour"]
    assert data["next"]["action"] == "wait"
    assert run_phase(m, root, "001-alpha", "plan", "opus", "r", "--resume").json["reason"] == "running"
    assert drive(m, root, "test", "--spec", "001-alpha").json["reason"] == "running"
    final = drive(m, root, "watch").watched
    assert final["status"] == "finished"
    assert [a["outcome"] for a in final["attempts"]] == ["usage-limit", "succeeded"]
    resumed = final["attempts"][1]
    assert (resumed["auto"], resumed["resume"], resumed["session_id"], resumed["model"], resumed["reason"]) == (
        True, True, view["session_id"], "opus", AUTO_REASON)
    assert final["attempts"][0]["auto_resume"] == "started"
    assert final["failures"] == {}
    assert calls(tmp_path)[1]["argv"][6:8] == ["--resume", view["session_id"]]
    assert len(calls(tmp_path)) == 2  # the driver did not start the next phase
    assert read_state(root)["driver"] is None
    waiting_until = m.parse_ts(first["waiting_until"])
    reset = m.parse_ts(view["limit"]["resets_at"])
    assert reset + TIMING["margin_seconds"] <= waiting_until <= reset + TIMING["margin_seconds"] + 1


def test_watch_started_while_waiting_does_not_report_at_once(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, limit_scenario(60))
    first = run_phase(m, root, "001-alpha", "plan").watched
    assert first["status"] == "waiting"
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(dict(TIMING, watch_seconds=0.6)))
    started = time.monotonic()
    second = drive(m, root, "watch").watched
    assert time.monotonic() - started >= 0.5
    assert second["status"] == "waiting" and second["waiting_until"] == first["waiting_until"]
    cancel = drive(m, root, "cancel")
    assert cancel.code == 0 and cancel.json == {"cancel_requested": True, "waiting_until": first["waiting_until"]}
    assert drive(m, root, "cancel").code == 0  # an existing cancel file counts as success
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(TIMING))
    final = drive(m, root, "watch").watched
    assert final["status"] == "finished" and final["attempts"][-1]["auto_resume"] == "cancelled"
    assert not (root / ".specify/sdd-drive/cancel").exists()
    assert len(calls(tmp_path)) == 1
    assert status(m, root)["next"]["action"] == "resume"


def test_two_watches_in_a_row_do_not_report_the_same_wait(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, limit_scenario(1.5), {"test_command": PASS_CMD})
    assert run_phase(m, root, "001-alpha", "plan").json["status"] == "waiting"
    second = drive(m, root, "watch").watched
    assert second["status"] == "finished"
    assert [a["outcome"] for a in second["attempts"]] == ["usage-limit", "succeeded"]


def test_cancel_without_a_waiting_driver(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    result = drive(m, root, "cancel")
    assert (result.code, result.json["reason"]) == (1, "not-waiting")
    assert not (root / ".specify/sdd-drive").exists()


def test_second_limit_after_the_automatic_resume_stops(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, limit_scenario(1), limit_scenario(60))
    assert run_phase(m, root, "001-alpha", "plan").json["status"] == "waiting"
    final = drive(m, root, "watch").watched
    assert [a["auto_resume"] for a in final["attempts"]] == ["started", "already-auto"]
    assert final["status"] == "finished" and len(calls(tmp_path)) == 2
    nxt = status(m, root)["next"]
    assert (nxt["action"], nxt["auto_resume"]) == ("resume", "already-auto")
    # A run started by the maintainer may wait once more.
    scenarios(monkeypatch, limit_scenario(60))
    again = run_phase(m, root, "001-alpha", "plan", "opus", "Resuming.", "--resume").watched
    assert again["status"] == "waiting" and again["attempts"][0]["auto"] is False
    drive(m, root, "cancel")
    assert drive(m, root, "watch").watched["attempts"][-1]["auto_resume"] == "cancelled"


def test_changed_worktree_while_waiting_skips_the_resume(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, limit_scenario(1.5))
    assert run_phase(m, root, "001-alpha", "plan").json["status"] == "waiting"
    write_tree(root, {"mine.txt": "x"})
    final = drive(m, root, "watch").watched
    assert final["attempts"][-1]["auto_resume"] == "skipped-changed" and len(calls(tmp_path)) == 1
    assert status(m, root)["dirty"] == ["mine.txt"]


def test_reset_already_past_waits_only_the_margin(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, limit_scenario(1, sleep=2.5), {"test_command": PASS_CMD})
    first = run_phase(m, root, "001-alpha", "plan").watched
    assert first["status"] == "waiting"
    ended = m.parse_ts(read_state(root)["attempts"][0]["ended_at"])
    assert m.parse_ts(first["waiting_until"]) - ended <= TIMING["margin_seconds"] + 2
    assert drive(m, root, "watch").watched["attempts"][-1]["outcome"] == "succeeded"


def test_vanished_driver_is_finalized_as_lost(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    limit = {"waitable": True, "types": ["five_hour"], "resets_at": T1, "overage_status": None}
    write_state(root, blank_state(attempts=[attempt(1, outcome="usage-limit", limit=limit, auto_resume="waiting",
                                                    detail={"code": "usage-limit", "paths": [], "text": None})],
                                  driver={"token": UUID2, "pid": 4242, "phase": "waiting", "attempt": 1,
                                          "waiting_until": T1, "started_at": T0}))
    data = status(m, root)
    assert data["running"] is False and data["pending_finalize"] is True and data["next"]["action"] == "finalize"
    result = drive(m, root, "finalize").json
    assert (result["outcome"], result["auto_resume"]) == ("usage-limit", "lost")
    state = read_state(root)
    assert state["attempts"][0]["auto_resume"] == "lost" and state["driver"] is None
    nxt = status(m, root)["next"]
    assert (nxt["action"], nxt["auto_resume"]) == ("resume", "lost")


def kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.kill(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=30)


def test_driver_survives_when_the_run_process_tree_is_killed(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD, "sleep": 3})
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen([PY, str(SCRIPT), "run", "--spec", "001-alpha", "--phase", "plan", "--model", "opus",
                                "--reason", "Design."], cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, **kwargs)
    wait_for(lambda: state_file(root).exists() and read_state(root)["driver"] is not None)
    kill_tree(process)
    record = wait_for(lambda: read_state(root)["attempts"][0]["outcome"], seconds=60)
    assert record == "succeeded"
    wait_for(lambda: read_state(root)["driver"] is None and not m.lock_held(root))
    assert status(m, root)["specs"][0]["state"] == "planned"


def test_run_reports_finished_with_null_outcome_when_the_driver_is_killed(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD, "sleep": 20})
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen([PY, str(SCRIPT), "run", "--spec", "001-alpha", "--phase", "plan", "--model", "opus",
                                "--reason", "Design."], cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, **kwargs)
    try:
        driver = wait_for(lambda: state_file(root).exists() and read_state(root)["driver"])
        # Kill the driver and the child it started, so nothing keeps running; the record is left behind.
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(driver["pid"])], capture_output=True)
        else:
            try:
                os.killpg(driver["pid"], signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                os.kill(driver["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
        out, err = process.communicate(timeout=60)
    finally:
        if process.poll() is None:
            kill_tree(process)
    result = Result(process.returncode, out, err)
    data = result.watched
    assert data["status"] == "finished", result.describe()
    last = data["attempts"][-1]
    assert last["outcome"] is None and last["detail"] is None, result.describe()
    state = read_state(root)
    assert state["driver"] is not None and state["launch"] is None
    assert status(m, root)["next"]["action"] == "finalize"


# ======================================================== T044 clear


def test_clear_writes_an_empty_record(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}})
    write_state(root, blank_state(baseline=["001-alpha"], attempts=[attempt(1)]))
    folder = root / ".specify/sdd-drive"
    (folder / "cancel").write_bytes(b"")
    (folder / ".state.json.x.tmp").write_bytes(b"")
    (folder / ".cancel.y.tmp").write_bytes(b"")
    assert status(m, root)["own_dir"] == "ours"
    result = drive(m, root, "clear")
    assert result.code == 0 and result.json == {"cleared": True, "baseline_reset": True}
    assert read_state(root) == blank_state(baseline=[], baseline_reset=True)
    assert sorted(p.name for p in folder.iterdir()) == [".gitignore", "lock", "state.json"]
    assert status(m, root)["specs"][0]["baseline"] is False
    assert drive(m, root, "clear").json == {"cleared": True, "baseline_reset": True}


def test_clear_works_when_the_record_is_unreadable_and_creates_gitignore(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    folder = root / ".specify/sdd-drive"
    folder.mkdir(parents=True)
    (folder / "state.json").write_bytes(b"{broken")
    assert drive(m, root, "status").json["reason"] == "state-unreadable"
    assert drive(m, root, "clear").code == 0
    assert (folder / ".gitignore").read_bytes() == OWN_GITIGNORE
    assert status(m, root)["next"]["action"] == "run"


def test_clear_refuses_while_running_and_on_conflict(m, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    write_state(root, blank_state(launch={"token": UUID2, "at": iso(1)}))
    assert drive(m, root, "clear").json["reason"] == "running"
    write_state(root, blank_state(driver={"token": UUID2, "pid": 1, "phase": "running", "attempt": 1,
                                          "waiting_until": None, "started_at": T0}))
    assert drive(m, root, "clear").json["reason"] == "running"
    write_state(root, blank_state())
    with hold_lock(root):
        assert drive(m, root, "clear").json["reason"] == "running"
    (root / ".specify/sdd-drive/mine.txt").write_bytes(b"x")
    before = tree_snapshot(root)
    assert drive(m, root, "clear").json["reason"] == "conflict"
    assert tree_snapshot(root) == before
