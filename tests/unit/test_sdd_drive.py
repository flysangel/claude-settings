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

    @property
    def json(self) -> dict:
        return json.loads(self.out.decode("utf-8"))

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
        git_run(root, "config", "user.name", "test")
        git_run(root, "config", "user.email", "test@example.invalid")
        git_run(root, "config", "core.autocrlf", "false")
        if commit:
            commit_all(root, "initial")
    return root


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
    return json.loads(state_file(root).read_bytes().decode("utf-8"))


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
    """Another process holds .specify/sdd-drive/lock until the block ends."""
    folder = root / ".specify" / "sdd-drive"
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".gitignore").exists():
        (folder / ".gitignore").write_bytes(OWN_GITIGNORE)
    holder = subprocess.Popen([PY, "-c", LOCK_HOLDER, str(folder / "lock")], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE)
    try:
        assert holder.stdout.readline().strip() == b"locked"
        yield holder
    finally:
        if holder.poll() is None:
            holder.stdin.close()
            holder.wait(timeout=30)


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
    assert result.code == 0
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

    def broken(path, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(drive_module.G(), "atomic_write", broken)
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
    assert result.code == 0
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
    assert result.json["attempts"][0]["detail"]["text"] == SECRET_TEXT
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


def test_held_lock_reports_running_and_refuses_writers(drive_module, tmp_path):
    root = make_project(tmp_path, specs={"001-alpha": {"plan": True, "tasks": (1, 1)}})
    write_state(root, blank_state(attempts=[attempt(1, phase="implement")]))
    with hold_lock(root):
        data = status(drive_module, root)
        assert data["running"] is True and data["next"]["action"] == "wait"
        before = tree_snapshot(root)
        for argv in (["run", "--spec", "001-alpha", "--phase", "check", "--model", "opus", "--reason", "r"],
                     ["test", "--spec", "001-alpha"], ["finalize"], ["clear"]):
            result = drive(drive_module, root, *argv)
            assert (result.code, result.json["reason"]) == (1, "running"), argv
        assert tree_snapshot(root) == before
    assert status(drive_module, root)["running"] is False


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
    assert watched.code == 0 and watched.json["status"] == "launch-failed"


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
    assert result.json["missing"] == ["speckit-tasks", "speckit-implement"]

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
    assert result.code == 0
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
    assert result.code == 0
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
    assert result.code == 0 and result.json["status"] == "running"
    state = read_state(root)
    assert state["attempts"][0]["outcome"] is None and state["launch"]["token"]
    assert status(m, root)["next"]["action"] == "wait"


def test_run_start_failure_is_launch_failed(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    monkeypatch.setattr(m, "start_driver", lambda root, token: False)
    result = run_phase(m, root, "001-alpha", "plan")
    assert result.code == 0
    data = result.json
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
    call = calls(tmp_path)[0]
    session = read_state(root)["attempts"][0]["session_id"]
    assert call["argv"][:12] == ["-p", "--output-format", "stream-json", "--verbose", "--model", "opus",
                                 "--session-id", session, "--json-schema", json.dumps(m.REPORT_SCHEMA, separators=(",", ":")),
                                 "--permission-mode", "acceptEdits"]
    assert call["argv"][12:] == ["--permission-prompts", "none", "--allowedTools", "Bash", "Skill",
                                 "--disallowedTools", "AskUserQuestion", "Bash(git push*)"]
    assert call["stdin"] == expected_brief
    assert Path(call["cwd"]).resolve() == root.resolve()
    assert result.json["attempts"][0]["model_used"] == ["claude-opus-test"]


def test_three_phases_succeed_and_record_worktree_and_task_ids(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD, "tasks": 4})
    for phase, after in (("plan", "planned"), ("tasks", "tasked"), ("implement", "implementing")):
        result = run_phase(m, root, "001-alpha", phase)
        data = result.json
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
    data = run_phase(m, root, "001-alpha", phase).json
    assert data["attempts"][0]["outcome"] == "verify-failed"
    assert data["attempts"][0]["detail"]["code"] == code
    assert data["attempts"][0]["counts_as_failure"] is True


def test_driver_clears_launch_writes_driver_and_clears_it(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD, "sleep": 1.5})
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(dict(TIMING, watch_seconds=0.3)))
    first = run_phase(m, root, "001-alpha", "plan")
    assert first.json["status"] == "running"
    seen = wait_for(lambda: read_state(root)["driver"])
    assert seen["phase"] == "running" and seen["attempt"] == 1 and read_state(root)["launch"] is None
    data = status(m, root)
    assert data["running"] is True and data["driver"]["phase"] == "running"
    monkeypatch.setenv("SDD_DRIVE_TEST_TIMING", json.dumps(TIMING))
    final = drive(m, root, "watch")
    assert final.json["status"] == "finished" and final.json["attempts"][0]["outcome"] == "succeeded"
    assert read_state(root)["driver"] is None
    # the driver did not start the next phase by itself
    assert len(calls(tmp_path)) == 1


def test_watch_output_fields(m, tmp_path, monkeypatch):
    root = make_project(tmp_path, specs={"001-alpha": {}})
    scenarios(monkeypatch, {"test_command": PASS_CMD,
                            "result": {"permission_denials": [{"tool_name": "WebFetch", "tool_input": {"url": "x"}},
                                                              {"tool_name": "WebFetch", "tool_input": {}}]}})
    run_phase(m, root, "001-alpha", "plan", "opus", "Design.")
    data = drive(m, root, "watch").json
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
    data = drive(m, root, "watch").json
    assert data["status"] == "finished" and data["attempts"][0]["outcome"] == "succeeded"


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
            data = run_phase(m, root, nxt["spec"], nxt["phase"]).json
            assert data["attempts"][-1]["outcome"] == "succeeded", data
    assert order == [("001-alpha", p) for p in ("plan", "tasks", "implement", "test", "check")] + \
                    [("002-beta", p) for p in ("plan", "tasks", "implement", "test", "check")]
    assert branch_of(root) == "002-beta"
    assert git_run(root, "merge-base", "--is-ancestor", "001-alpha", "002-beta") == ""
