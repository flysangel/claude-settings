# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Drive every spec of a Spec Kit project through plan, tasks, implement, test and check, one at a time.

Usage:
    uv run sdd_drive.py status                                   prerequisites, state of every spec, next step
    uv run sdd_drive.py brief    --spec <dir> --phase <phase>    print the work description for a child session
    uv run sdd_drive.py run      --spec <dir> --phase <phase> --model <model> --reason <text> [--resume] [--fresh]
                                                                 prepare, start the driver, then wait like watch
    uv run sdd_drive.py watch    [--minutes <n>]                 wait for the driver to finish or to start waiting
    uv run sdd_drive.py cancel                                   ask the waiting driver not to resume
    uv run sdd_drive.py test     --spec <dir>                    run the spec's test command and record it
    uv run sdd_drive.py finalize                                 record an attempt that ended without a result
    uv run sdd_drive.py clear                                    reset this skill's records

Run it from the root of the target project. Output is one JSON object on stdout (brief prints plain text).
The internal command `_drive --token <uuid>` is started only by `run`. Nothing runs when this file is imported.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_STATE = 3

# ------------------------------------------------------------------ neighbour

_cache: dict[str, object] = {}


def neighbour_path() -> Path:
    """<this file>/../../../sdd-grill/scripts/sdd_grill.py, in the repository and once installed."""
    return Path(os.path.abspath(__file__)).parents[2] / "sdd-grill" / "scripts" / "sdd_grill.py"


def load_grill():
    """sdd-grill's script as a module, or None when it is missing or fails to load."""
    if "grill" in _cache:
        return _cache["grill"]
    path = neighbour_path()
    if not path.is_file():
        return None
    loaded = sys.modules.get("sdd_grill")
    loaded_file = getattr(loaded, "__file__", None)
    if loaded_file:
        try:
            if os.path.samefile(loaded_file, path):
                _cache["grill"] = loaded
                return loaded
        except OSError:
            pass
    name = "sdd_grill" if "sdd_grill" not in sys.modules else f"_sdd_drive_sdd_grill_{id(path)}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        return None
    _cache["grill"] = module
    return module


def G():
    return _cache["grill"]


# ------------------------------------------------------------------ constants

PHASES = ("plan", "tasks", "implement", "check")
FAILURE_KEYS = ("plan", "tasks", "implement", "test", "check")
PHASE_SKILLS = {"plan": "speckit-plan", "tasks": "speckit-tasks", "implement": "speckit-implement", "check": "speckit-converge"}
REQUIRED_SKILLS = ("speckit-plan", "speckit-tasks", "speckit-implement")

OWN_DIR = ".specify/sdd-drive"
GITIGNORE_NAME = ".gitignore"
STATE_NAME = "state.json"
LOCK_NAME = "lock"
CANCEL_NAME = "cancel"
OWN_FILES = (GITIGNORE_NAME, STATE_NAME, LOCK_NAME, CANCEL_NAME)
OWN_GITIGNORE = "# Created by sdd-drive. Local run records; never committed.\n*\n"
TEMP_FILE = re.compile(r"^\.(state\.json|\.gitignore|cancel)\..+\.tmp$")  # atomic_write's temporary files
FEATURE_JSON = ".specify/feature.json"
PLAN_TEMPLATE = ".specify/templates/plan-template.md"
TASKS_TEMPLATE = ".specify/templates/tasks-template.md"
CONSTITUTION = ".specify/memory/constitution.md"

SECRET_TEXT = "(not shown: looks like a secret)"
SECRET_PATH = "(not shown)"
SECRET_LINE = "(line not shown: looks like a secret)"
AUTO_REASON = "Automatic resume after the usage limit reset."

LAUNCH_SECONDS = 60
DEFAULT_POLL = 30.0
DEFAULT_MARGIN = 120.0
DEFAULT_MINUTES = 110

OUTCOMES = ("launch-failed", "usage-limit", "api-error", "interrupted", "failed", "verify-failed", "succeeded", "gaps-found")
FAILURE_OUTCOMES = ("failed", "verify-failed", "gaps-found")
RESUMABLE = ("usage-limit", "api-error", "interrupted")
DETAIL_CODES = (
    "launch", "usage-limit", "api-error", "no-result", "no-report", "child-failed", "plan-missing", "tasks-missing",
    "tasks-unfinished", "tasks-removed", "protected-changed", "pushed", "uncommitted", "resume-failed",
    "check-no-tasks", "check-rewrote-tasks", "check-touched-files", "report-mismatch",
)
LIMIT_TYPES = ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "seven_day_overage_included", "overage", "unknown")
WINDOW_TYPES = ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet")
OVERAGE_STATUSES = ("allowed", "allowed_warning", "rejected")
AUTO_RESUMES = ("waiting", "started", "cancelled", "skipped-changed", "lost", "not-waitable", "already-auto")
CONVERGENCES = ("converged", "tasks-appended")
DRIVER_PHASES = ("running", "waiting", "resuming")

MODEL = re.compile(r"^[A-Za-z0-9._\[\]-]{1,64}$")
UUID_FORM = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TIME_FORM = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HASH_FORM = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_FORM = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
TASK_ID = re.compile(r"^T\d{3,}$")
SPEC_PREFIX = re.compile(r"^(?:\d{8}-\d{6}|\d{3,})-")  # the same prefixes as sdd-grill's spec_number
TASK_LINE = re.compile(r"^\s*- \[( |x|X)\] (T\d{3,})\b")
USAGE_TEXT = re.compile(r"usage limit|hit your limit|rate limit", re.IGNORECASE)
PLACEHOLDER_COMMANDS = ("n/a", "none", "tbd")

STATE_KEYS = ("tool", "schema", "attempts", "baseline", "baseline_reset", "launch", "driver", "tests")
ATTEMPT_KEYS = (
    "id", "spec", "phase", "session_id", "resume", "model", "model_used", "reason", "started_at", "ended_at", "outcome",
    "detail", "report", "worktree", "task_ids", "convergence", "tasks_hash", "appended", "auto", "limit",
    "auto_resume", "permission_denials",
)
TEST_KEYS = ("spec", "tasks_hash", "command", "exit_code", "head", "at")
DETAIL_KEYS = ("code", "paths", "text")
LIMIT_KEYS = ("waitable", "types", "resets_at", "overage_status")
LAUNCH_KEYS = ("token", "at")
DRIVER_KEYS = ("token", "pid", "phase", "attempt", "waiting_until", "started_at")
TOOL_NAME = re.compile(r"^[A-Za-z0-9_.:*()\-]{1,128}$")

REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary"],
    "properties": {
        "status": {"enum": ["completed", "failed"]},
        "convergence": {"enum": ["converged", "tasks-appended"]},
        "summary": {"type": "string", "maxLength": 1000},
        "failure": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "step", "reason"],
            "properties": {
                "kind": {"enum": ["requirements", "blocked-task", "tests", "tooling", "other"]},
                "step": {"type": "string", "maxLength": 200},
                "reason": {"type": "string", "maxLength": 1000},
            },
        },
        "tasks": {"type": "array", "items": {"type": "string", "pattern": "^T\\d{3,}$"}},
    },
}
FAILURE_KINDS = ("requirements", "blocked-task", "tests", "tooling", "other")

STATUS_KEYS = (
    "speckit", "missing", "claude", "git", "branch", "own_dir", "running", "running_attempt", "driver", "last_attempt",
    "pending_finalize", "dirty", "leftovers", "specs", "next",
)
NEXT_KEYS = (
    "action", "spec", "phase", "branch", "session_id", "model", "failures", "last_outcome", "limit", "auto_resume",
    "test_command", "covers", "hints",
)

USAGE = (
    "usage: sdd_drive.py status | brief --spec <dir> --phase <phase> | run --spec <dir> --phase <phase> --model <model> "
    "--reason <text> [--resume] [--fresh] | watch [--minutes <n>] | cancel | test --spec <dir> | finalize | clear"
)
MESSAGES = {
    "dependency": "sdd-drive needs the sdd-grill skill installed next to it",
    "speckit-missing": "Spec Kit is not set up in this project; run /sdd-init first",
    "speckit-incomplete": "Spec Kit in this project lacks skills sdd-drive needs: {}",
    "no-specs": "there is no spec under specs/",
    "claude-missing": "the claude command was not found; child sessions cannot be started",
    "conflict": ".specify/sdd-drive/ holds files sdd-drive did not create; nothing was read or written",
    "state-unreadable": "the records in .specify/sdd-drive/state.json are unreadable at {}",
    "running": "another sdd-drive run is in progress in this project",
    "secret": "the reason looks like a secret; describe the choice without the value",
    "not-next": "{} is not the next step; run status again",
    "pending-finalize": "an attempt ended without a result; run finalize first",
    "dirty": "the working tree has uncommitted changes that sdd-drive did not leave behind",
    "branch-diverged": "branch {} exists and has diverged from the current HEAD",
    "no-test-command": "plan.md of {} has no usable test command on its **Testing**: line",
    "nothing-to-finalize": "there is no attempt to finalize",
    "not-waiting": "no driver is waiting for a usage limit to reset",
    "no-driver": "no driver is running and there is no result to report; run status",
    "os-error": "could not write or run git: {}",
}


class Usage(Exception):
    pass


class Failure(Exception):
    def __init__(self, reason: str, message: str, code: int = EXIT_FAILED, **fields):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.code = code
        self.fields = fields


def fail(reason: str, *args, code: int | None = None, **fields) -> Failure:
    message = MESSAGES[reason].format(*args) if args else MESSAGES[reason]
    if code is None:
        code = EXIT_STATE if reason in ("dependency", "speckit-missing", "speckit-incomplete", "no-specs",
                                        "claude-missing", "state-unreadable") else EXIT_FAILED
    return Failure(reason, message, code, **fields)


# ---------------------------------------------------------------------- time


def now_ts() -> float:
    return time.time()


def utc_now() -> str:
    return format_ts(now_ts())


def format_ts(ts: float) -> str:
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(text: str) -> float:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


# ----------------------------------------------------------------- utilities


def dumps(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def secret(text: str) -> bool:
    return G().looks_like_secret(text)


def clean_text(text: str | None, limit: int | None = None) -> str | None:
    if text is None:
        return None
    if limit is not None and len(text) > limit:
        text = text[:limit]
    return SECRET_TEXT if secret(text) else text


def clean_path(path: str) -> str:
    return SECRET_PATH if secret(path) else path


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return "sha256:" + G().content_hash(path.read_bytes())


def read_text(path: Path) -> str | None:
    try:
        return G().normalize_newlines(path.read_bytes()).decode("utf-8", errors="replace")
    except OSError:
        return None


WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000


SHARING_SECONDS = 5.0


def shared(action):
    """Run a file action; on Windows retry it for a few seconds while it fails with PermissionError.

    Windows refuses to replace a file that another process has open, and refuses to open a file that is being
    replaced; the driver writes state.json while watch and status read it, so both sides see these brief
    sharing violations. On other systems a PermissionError is permanent and is raised at once.
    """
    deadline = time.monotonic() + SHARING_SECONDS
    while True:
        try:
            return action()
        except PermissionError:
            if not WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def atomic_write(path: Path, data: bytes) -> None:
    """Write to a temporary file in the same folder, then replace path with it (see shared)."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        shared(lambda: os.replace(tmp, path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run_cmd(args: list[str], root: Path, **kwargs) -> subprocess.CompletedProcess:
    if WINDOWS:
        kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(args, cwd=root, capture_output=True, stdin=subprocess.DEVNULL, **kwargs)


def timing() -> dict:
    """Test-only timing (SDD_DRIVE_TEST_TIMING), validated in main."""
    raw = os.environ.get("SDD_DRIVE_TEST_TIMING")
    if not raw:
        return {}
    return json.loads(raw)


def poll_seconds() -> float:
    return float(timing().get("poll_seconds", DEFAULT_POLL))


def margin_seconds() -> float:
    return float(timing().get("margin_seconds", DEFAULT_MARGIN))


def validate_environment() -> None:
    raw = os.environ.get("SDD_DRIVE_CLAUDE")
    if raw is not None:
        try:
            value = json.loads(raw)
        except ValueError:
            raise Usage
        if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
            raise Usage
    raw = os.environ.get("SDD_DRIVE_TEST_TIMING")
    if raw is not None:
        try:
            value = json.loads(raw)
        except ValueError:
            raise Usage
        if not isinstance(value, dict) or set(value) != {"poll_seconds", "margin_seconds", "watch_seconds"}:
            raise Usage
        for item in value.values():
            if isinstance(item, bool) or not isinstance(item, (int, float)) or item < 0:
                raise Usage


def claude_command() -> list[str] | None:
    raw = os.environ.get("SDD_DRIVE_CLAUDE")
    if raw is not None:
        return json.loads(raw)
    found = shutil.which("claude")
    return [found] if found else None


# ------------------------------------------------------------ own folder


def own_dir(root: Path) -> Path:
    return root / OWN_DIR


def own_dir_state(root: Path) -> str:
    """none, ours or conflict."""
    folder = own_dir(root)
    if not folder.exists() and not folder.is_symlink():
        return "none"
    if not folder.is_dir() or folder.is_symlink():
        return "conflict"
    for entry in folder.iterdir():
        try:
            mode = entry.lstat().st_mode
        except FileNotFoundError:
            # Gone since the listing: a temporary file just renamed over state.json, or cancel just removed by the
            # driver. What is no longer there is not a conflict.
            continue
        except OSError:
            # Windows: a file of ours that is being replaced or removed may refuse even its attributes.
            if entry.name in OWN_FILES or TEMP_FILE.match(entry.name):
                continue
            return "conflict"
        if not stat.S_ISREG(mode):
            return "conflict"
        if entry.name not in OWN_FILES and not TEMP_FILE.match(entry.name):
            return "conflict"
    gitignore = folder / GITIGNORE_NAME
    if gitignore.exists() and G().normalize_newlines(gitignore.read_bytes()) != OWN_GITIGNORE.encode("utf-8"):
        return "conflict"
    return "ours"


def ensure_own_dir(root: Path) -> None:
    folder = own_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / GITIGNORE_NAME).exists():
        atomic_write(folder / GITIGNORE_NAME, OWN_GITIGNORE.encode("utf-8"))


# --------------------------------------------------------------------- lock


class Lock:
    """An operating-system lock on .specify/sdd-drive/lock; released when the process ends."""

    def __init__(self, root: Path):
        self.path = own_dir(root) / LOCK_NAME
        self.handle = None

    def try_acquire(self, create: bool = True) -> bool:
        if not create and not self.path.is_file():
            return True
        if create:
            ensure_own_dir(self.path.parent.parent.parent)
            handle = open(self.path, "a+b")
        else:
            try:
                handle = open(self.path, "rb")
            except OSError:
                return True
        try:
            if WINDOWS:
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def acquire(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while True:
            if self.try_acquire():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if WINDOWS:
                import msvcrt

                self.handle.seek(0)
                try:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def lock_held(root: Path) -> bool:
    """True when another process holds the lock. Never creates a file."""
    probe = Lock(root)
    if not probe.try_acquire(create=False):
        return True
    probe.release()
    return False


# -------------------------------------------------------------------- state


class Unreadable(Exception):
    def __init__(self, path: str):
        super().__init__(path)
        self.path = path


def empty_state(baseline: list[str], reset: bool = False) -> dict:
    return {"tool": "sdd-drive", "schema": 1, "attempts": [], "baseline": list(baseline), "baseline_reset": reset,
            "launch": None, "driver": None, "tests": []}


def _need(cond: bool, path: str) -> None:
    if not cond:
        raise Unreadable(path)


def _keys(value, keys: tuple, path: str) -> None:
    _need(isinstance(value, dict) and tuple(value.keys()) == keys, path)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _time(value, path: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    _need(isinstance(value, str) and TIME_FORM.match(value) is not None, path)


def _hash(value, path: str, nullable: bool = True) -> None:
    if nullable and value is None:
        return
    _need(isinstance(value, str) and HASH_FORM.match(value) is not None, path)


def _scanned(value, path: str) -> None:
    _need(isinstance(value, str), path)
    _need(not secret(value), path)


def _ids(value, path: str) -> None:
    if value is None:
        return
    _need(isinstance(value, list) and all(isinstance(v, str) and TASK_ID.match(v) for v in value), path)


def spec_name_ok(value) -> bool:
    return (isinstance(value, str) and "/" not in value and "\\" not in value
            and SPEC_PREFIX.match(value) is not None)


def report_valid(report) -> bool:
    """The child's structured output against REPORT_SCHEMA (and: failed needs failure)."""
    if not isinstance(report, dict):
        return False
    allowed = ("status", "convergence", "summary", "failure", "tasks")
    if any(key not in allowed for key in report) or "status" not in report or "summary" not in report:
        return False
    if report["status"] not in ("completed", "failed"):
        return False
    if "convergence" in report and report["convergence"] not in CONVERGENCES:
        return False
    if not isinstance(report["summary"], str) or len(report["summary"]) > 1000:
        return False
    if "failure" in report:
        failure = report["failure"]
        if not isinstance(failure, dict) or set(failure) != {"kind", "step", "reason"}:
            return False
        if failure["kind"] not in FAILURE_KINDS:
            return False
        if not isinstance(failure["step"], str) or len(failure["step"]) > 200:
            return False
        if not isinstance(failure["reason"], str) or len(failure["reason"]) > 1000:
            return False
    if "tasks" in report:
        tasks = report["tasks"]
        if not isinstance(tasks, list) or not all(isinstance(t, str) and TASK_ID.match(t) for t in tasks):
            return False
    if report["status"] == "failed" and "failure" not in report:
        return False
    return True


def clean_report(report: dict) -> dict:
    result = dict(report)
    result["summary"] = clean_text(result["summary"])
    if "failure" in result:
        failure = dict(result["failure"])
        failure["step"] = clean_text(failure["step"])
        failure["reason"] = clean_text(failure["reason"])
        result["failure"] = failure
    return result


def validate_report_field(report, path: str) -> None:
    if report is None:
        return
    _need(report_valid(report), path)
    _scanned(report["summary"], path + ".summary")
    if "failure" in report:
        _scanned(report["failure"]["step"], path + ".failure.step")
        _scanned(report["failure"]["reason"], path + ".failure.reason")


def validate_limit(limit, path: str) -> None:
    if limit is None:
        return
    _keys(limit, LIMIT_KEYS, path)
    _need(isinstance(limit["waitable"], bool), path + ".waitable")
    types = limit["types"]
    _need(isinstance(types, list) and all(t in LIMIT_TYPES for t in types), path + ".types")
    if limit["waitable"]:
        _time(limit["resets_at"], path + ".resets_at")
    else:
        _need(limit["resets_at"] is None, path + ".resets_at")
    _need(limit["overage_status"] is None or limit["overage_status"] in OVERAGE_STATUSES, path + ".overage_status")


def validate_attempt(attempt, path: str) -> None:
    _keys(attempt, ATTEMPT_KEYS, path)
    _need(_is_int(attempt["id"]) and attempt["id"] > 0, path + ".id")
    _need(spec_name_ok(attempt["spec"]), path + ".spec")
    _need(attempt["phase"] in PHASES, path + ".phase")
    _need(isinstance(attempt["session_id"], str) and UUID_FORM.match(attempt["session_id"]) is not None,
          path + ".session_id")
    _need(isinstance(attempt["resume"], bool), path + ".resume")
    _need(isinstance(attempt["model"], str) and MODEL.match(attempt["model"]) is not None, path + ".model")
    used = attempt["model_used"]
    _need(isinstance(used, list) and all(isinstance(m, str) and MODEL.match(m) for m in used), path + ".model_used")
    reason = attempt["reason"]
    _need(isinstance(reason, str) and 1 <= len(reason) <= 300 and "\n" not in reason and "\r" not in reason,
          path + ".reason")
    _scanned(reason, path + ".reason")
    _time(attempt["started_at"], path + ".started_at")
    outcome = attempt["outcome"]
    _need(outcome is None or outcome in OUTCOMES, path + ".outcome")
    if outcome is None:
        _need(attempt["ended_at"] is None, path + ".ended_at")
    else:
        _time(attempt["ended_at"], path + ".ended_at")
    detail = attempt["detail"]
    if detail is not None:
        _keys(detail, DETAIL_KEYS, path + ".detail")
        _need(detail["code"] in DETAIL_CODES, path + ".detail.code")
        _need(isinstance(detail["paths"], list), path + ".detail.paths")
        for index, item in enumerate(detail["paths"]):
            _scanned(item, f"{path}.detail.paths[{index}]")
        if detail["text"] is not None:
            _scanned(detail["text"], path + ".detail.text")
            _need(len(detail["text"]) <= 500, path + ".detail.text")
    validate_report_field(attempt["report"], path + ".report")
    _hash(attempt["worktree"], path + ".worktree")
    _ids(attempt["task_ids"], path + ".task_ids")
    _need(attempt["convergence"] is None or attempt["convergence"] in CONVERGENCES, path + ".convergence")
    _hash(attempt["tasks_hash"], path + ".tasks_hash")
    _ids(attempt["appended"], path + ".appended")
    _need(isinstance(attempt["auto"], bool), path + ".auto")
    validate_limit(attempt["limit"], path + ".limit")
    _need(attempt["auto_resume"] is None or attempt["auto_resume"] in AUTO_RESUMES, path + ".auto_resume")
    denials = attempt["permission_denials"]
    _need(isinstance(denials, list) and all(isinstance(d, str) and TOOL_NAME.match(d) for d in denials),
          path + ".permission_denials")


def validate_state(data) -> dict:
    _keys(data, STATE_KEYS, "(top level)")
    _need(data["tool"] == "sdd-drive", "tool")
    _need(data["schema"] == 1 and _is_int(data["schema"]), "schema")
    _need(isinstance(data["attempts"], list), "attempts")
    last_id = 0
    for index, attempt in enumerate(data["attempts"]):
        path = f"attempts[{index}]"
        validate_attempt(attempt, path)
        _need(attempt["id"] > last_id, path + ".id")
        last_id = attempt["id"]
    baseline = data["baseline"]
    _need(isinstance(baseline, list) and all(spec_name_ok(b) for b in baseline) and len(set(baseline)) == len(baseline),
          "baseline")
    _need(isinstance(data["baseline_reset"], bool), "baseline_reset")
    launch = data["launch"]
    if launch is not None:
        _keys(launch, LAUNCH_KEYS, "launch")
        _need(isinstance(launch["token"], str) and UUID_FORM.match(launch["token"]) is not None, "launch.token")
        _time(launch["at"], "launch.at")
    driver = data["driver"]
    if driver is not None:
        _keys(driver, DRIVER_KEYS, "driver")
        _need(isinstance(driver["token"], str) and UUID_FORM.match(driver["token"]) is not None, "driver.token")
        _need(_is_int(driver["pid"]) and driver["pid"] > 0, "driver.pid")
        _need(driver["phase"] in DRIVER_PHASES, "driver.phase")
        _need(_is_int(driver["attempt"]) and driver["attempt"] > 0, "driver.attempt")
        _time(driver["waiting_until"], "driver.waiting_until", nullable=True)
        _time(driver["started_at"], "driver.started_at")
    _need(isinstance(data["tests"], list), "tests")
    for index, test in enumerate(data["tests"]):
        path = f"tests[{index}]"
        _keys(test, TEST_KEYS, path)
        _need(spec_name_ok(test["spec"]), path + ".spec")
        _hash(test["tasks_hash"], path + ".tasks_hash", nullable=False)
        _scanned(test["command"], path + ".command")
        _need(_is_int(test["exit_code"]), path + ".exit_code")
        _need(test["head"] is None or (isinstance(test["head"], str) and HEAD_FORM.match(test["head"]) is not None),
              path + ".head")
        _time(test["at"], path + ".at")
    return data


def state_path(root: Path) -> Path:
    return own_dir(root) / STATE_NAME


def load_state(root: Path) -> dict | None:
    """The validated records, or None when there are none yet. Raises Unreadable."""
    path = state_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(shared(path.read_bytes).decode("utf-8"))
    except (OSError, ValueError):
        raise Unreadable("(file)")
    return validate_state(data)


def current_state(root: Path) -> dict:
    """The records, or a fresh record with the baseline computed now (not written)."""
    state = load_state(root)
    if state is None:
        state = empty_state(computed_baseline(root))
    return state


def save_state(root: Path, state: dict) -> None:
    """Write the records (same-folder temporary file, then replace); the first write freezes the baseline."""
    ensure_own_dir(root)
    validate_state(json.loads(dumps(state)))
    atomic_write(state_path(root), dumps(state))


def apply_secrets(attempt: dict) -> dict:
    """Replace the strings that come from outside before they are written (reason is checked by run)."""
    detail = attempt.get("detail")
    if detail is not None:
        detail["paths"] = [clean_text(p) for p in detail["paths"]]
        detail["text"] = clean_text(detail["text"], 500)
    if attempt.get("report") is not None:
        attempt["report"] = clean_report(attempt["report"])
    return attempt


def make_detail(code: str, paths: list[str] | None = None, text: str | None = None) -> dict:
    return {"code": code, "paths": list(paths or []), "text": text}


# --------------------------------------------------------------------- git


def is_git(root: Path) -> bool:
    try:
        done = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], root)
    except OSError:
        return False
    return done.returncode == 0 and done.stdout.decode("utf-8", "replace").strip() == "true"


def git_out(root: Path, *args: str) -> str:
    done = run_cmd(["git", *args], root)
    if done.returncode != 0:
        raise OSError(f"git {args[0]} failed")
    return done.stdout.decode("utf-8", "replace")


def git_ok(root: Path, *args: str) -> bool:
    return run_cmd(["git", *args], root).returncode == 0


def head(root: Path) -> str | None:
    return G().git_head(root)


def current_branch(root: Path) -> str | None:
    done = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", "replace").strip() or None


def git_prefix(root: Path) -> str:
    done = run_cmd(["git", "rev-parse", "--show-prefix"], root)
    return done.stdout.decode("utf-8", "replace").strip() if done.returncode == 0 else ""


def excluded(path: str) -> bool:
    return path == FEATURE_JSON or path == OWN_DIR or path.startswith(OWN_DIR + "/")


def status_entries(root: Path, extra: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """(XY, path relative to the project root) from git status, excluding feature.json and our folder."""
    out = run_cmd(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", *extra], root)
    if out.returncode != 0:
        raise OSError("git status failed")
    prefix = git_prefix(root)
    parts = out.stdout.decode("utf-8", "replace").split("\0")
    result = []
    index = 0
    while index < len(parts):
        item = parts[index]
        index += 1
        if len(item) < 4:
            continue
        code, path = item[:2], item[3:]
        if code[0] in "RC":
            index += 1  # the original path follows
        if prefix:
            if not path.startswith(prefix):
                continue
            path = path[len(prefix):]
        if excluded(path.rstrip("/")):
            continue
        result.append((code, path))
    return result


def dirty_paths(root: Path) -> list[str]:
    return sorted({path for code, path in status_entries(root) if code != "!!"})


def worktree_fingerprint(root: Path) -> str | None:
    """SHA-256 over the status entries and the content of each path; None outside git."""
    if not is_git(root):
        return None
    digest = hashlib.sha256()
    for code, path in sorted(status_entries(root)):
        target = root / path
        content = G().content_hash(target.read_bytes()) if target.is_file() else "absent"
        digest.update(f"{code}\0{content}\0".encode("utf-8"))
        digest.update(hashlib.sha256(path.encode("utf-8")).digest())
    return "sha256:" + digest.hexdigest()


def remote_refs(root: Path) -> str:
    done = run_cmd(["git", "for-each-ref", "--format=%(refname) %(objectname)", "refs/remotes"], root)
    return done.stdout.decode("utf-8", "replace")


def prepare_branch(root: Path, name: str) -> None:
    """Stay, create from HEAD, or switch when HEAD is an ancestor; never merge or reset."""
    branch = current_branch(root)
    if branch == name:
        return
    if git_ok(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
        if not git_ok(root, "merge-base", "--is-ancestor", "HEAD", f"refs/heads/{name}"):
            raise fail("branch-diverged", name)
        if run_cmd(["git", "switch", "--quiet", name], root).returncode != 0:
            raise fail("os-error", f"git switch {name} failed")
        return
    if run_cmd(["git", "switch", "--quiet", "-c", name], root).returncode != 0:
        raise fail("os-error", f"git switch -c {name} failed")


def set_feature_directory(root: Path, spec: str) -> None:
    path = root / FEATURE_JSON
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
    data["feature_directory"] = f"specs/{spec}"
    atomic_write(path, dumps(data))


PROTECTED_DIRS = (".specify/templates", ".specify/scripts")


def protected_hashes(root: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {CONSTITUTION: file_sha(root / CONSTITUTION)}
    specs = root / "specs"
    if specs.is_dir():
        for folder in sorted(specs.iterdir()):
            if folder.is_dir():
                result[f"specs/{folder.name}/spec.md"] = file_sha(folder / "spec.md")
    bases = [root / d for d in PROTECTED_DIRS]
    skills = root / ".claude" / "skills"
    if skills.is_dir():
        bases += [p for p in sorted(skills.iterdir()) if p.is_dir() and p.name.startswith("speckit-")]
    for base in bases:
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    result[path.relative_to(root).as_posix()] = file_sha(path)
    return result


def changed_keys(before: dict, after: dict) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def tree_hashes(root: Path, git: bool) -> dict[str, str]:
    """Content hash of every file that is not ignored (outside .git, our folder and feature.json)."""
    ignored_dirs: set[str] = set()
    ignored_files: set[str] = set()
    if git:
        done = run_cmd(["git", "status", "--porcelain=v1", "-z", "--ignored", "--untracked-files=normal"], root)
        prefix = git_prefix(root)
        for item in done.stdout.decode("utf-8", "replace").split("\0"):
            if item.startswith("!! "):
                path = item[3:]
                if prefix:
                    if not path.startswith(prefix):
                        continue
                    path = path[len(prefix):]
                if path.endswith("/"):
                    ignored_dirs.add(path.rstrip("/"))
                else:
                    ignored_files.add(path)
    result: dict[str, str] = {}
    for current, dirs, names in os.walk(root):
        rel_dir = Path(current).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        keep = []
        for d in dirs:
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if d == ".git" or rel in ignored_dirs or excluded(rel):
                continue
            keep.append(d)
        dirs[:] = keep
        for name in names:
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if rel in ignored_files or excluded(rel):
                continue
            path = Path(current) / name
            if path.is_file():
                result[rel] = G().content_hash(path.read_bytes())
    return result


# --------------------------------------------------------------- spec state


def spec_dirs(root: Path) -> list[str]:
    names = [n for n in G().spec_folders(root) if G().spec_number(n) is not None]

    def key(name: str):
        number = G().spec_number(name)
        return (int(number.replace("-", "")), name)

    return sorted(names, key=key)


def first_heading(text: str) -> str | None:
    for line in text.split("\n"):
        if line.startswith("# "):
            return line
    return None


def same_as_template(root: Path, text: str, template: str) -> bool:
    template_text = read_text(root / template)
    return template_text is not None and template_text == text


def plan_generated(root: Path, spec: str) -> bool:
    text = read_text(root / "specs" / spec / "plan.md")
    if text is None or same_as_template(root, text, PLAN_TEMPLATE):
        return False
    heading = first_heading(text)
    return not (heading is not None and "[FEATURE]" in heading)


def task_entries(text: str) -> list[tuple[str, bool]]:
    result = []
    for line in text.split("\n"):
        match = TASK_LINE.match(line)
        if match:
            result.append((match.group(2), match.group(1) in "xX"))
    return result


def tasks_generated(root: Path, spec: str) -> bool:
    text = read_text(root / "specs" / spec / "tasks.md")
    if text is None or same_as_template(root, text, TASKS_TEMPLATE):
        return False
    heading = first_heading(text)
    if heading is not None and "[FEATURE NAME]" in heading:
        return False
    return bool(task_entries(text))


def tasks_hash(root: Path, spec: str) -> str | None:
    return file_sha(root / "specs" / spec / "tasks.md")


def task_counts(root: Path, spec: str) -> tuple[int, int, list[str]]:
    text = read_text(root / "specs" / spec / "tasks.md") or ""
    entries = task_entries(text)
    return len(entries), sum(1 for _, done in entries if not done), [i for i, _ in entries]


TESTING_LINE = re.compile(r"\*\*Testing\*\*:(.*)")


def test_command(root: Path, spec: str) -> tuple[str | None, str | None]:
    """(command, problem); problem is missing, placeholder or secret."""
    text = read_text(root / "specs" / spec / "plan.md") or ""
    for line in text.split("\n"):
        match = TESTING_LINE.search(line)
        if match:
            ticks = re.search(r"`([^`]*)`", match.group(1))
            if not ticks:
                return None, "missing"
            command = ticks.group(1).strip()
            if not command or command.lower() in PLACEHOLDER_COMMANDS:
                return None, "placeholder"
            if secret(command):
                return None, "secret"
            return command, None
    return None, "missing"


def computed_baseline(root: Path) -> list[str]:
    """Specs whose tasks exist and are all checked (used until the records are first written, D23)."""
    result = []
    for spec in spec_dirs(root):
        if tasks_generated(root, spec):
            total, open_, _ = task_counts(root, spec)
            if total and not open_:
                result.append(spec)
    return result


class Context:
    """Everything status needs, computed once from the files and the records."""

    def __init__(self, root: Path, state: dict):
        self.root = root
        self.state = state
        self.git = is_git(root)
        self.head = head(root) if self.git else None

    def attempts_for(self, spec: str, phase: str | None = None) -> list[dict]:
        return [a for a in self.state["attempts"] if a["spec"] == spec and (phase is None or a["phase"] == phase)]

    def is_baseline(self, spec: str) -> bool:
        return spec in self.state["baseline"] and not self.attempts_for(spec, "implement")

    def failures(self, spec: str) -> dict:
        counts = {key: 0 for key in FAILURE_KEYS}
        for attempt in self.attempts_for(spec):
            if attempt["outcome"] in FAILURE_OUTCOMES:
                counts[attempt["phase"]] += 1
        counts["test"] = sum(1 for t in self.state["tests"] if t["spec"] == spec and t["exit_code"] != 0)
        return {key: value for key, value in counts.items() if value}

    def spec_state(self, spec: str) -> dict:
        root = self.root
        total, open_, _ = task_counts(root, spec)
        if not plan_generated(root, spec):
            state, phase = "not-started", "plan"
        elif not tasks_generated(root, spec):
            state, phase = "planned", "tasks"
            total, open_ = 0, 0
        elif total - open_ == 0:
            state, phase = "tasked", "implement"
        elif open_:
            state, phase = "implementing", "implement"
        else:
            current = tasks_hash(root, spec)
            tests = [t for t in self.state["tests"] if t["spec"] == spec and t["tasks_hash"] == current]
            if self.is_baseline(spec):
                passed = bool(tests) and tests[-1]["exit_code"] == 0
                state, phase = ("done", None) if passed else ("implementing", "test")
            elif any(a["phase"] == "check" and a["outcome"] == "succeeded" and a["convergence"] == "converged"
                     and a["tasks_hash"] == current for a in self.attempts_for(spec)):
                state, phase = "done", None
            else:
                matching = [t for t in tests if not self.git or t["head"] == self.head]
                if matching and matching[-1]["exit_code"] == 0:
                    state, phase = "implementing", "check"
                else:
                    state, phase = "implementing", "test"
        if phase is not None and phase != "test":
            on_phase = self.attempts_for(spec, phase)
            if on_phase and on_phase[-1]["outcome"] in ("failed", "verify-failed"):
                state = "failed"
        if phase == "test":
            tests = [t for t in self.state["tests"] if t["spec"] == spec]
            if tests and tests[-1]["exit_code"] != 0:
                state = "failed"
        return {"spec": spec, "state": state, "next_phase": phase, "baseline": self.is_baseline(spec),
                "tasks_total": total, "tasks_open": open_, "failures": self.failures(spec)}

    def specs(self) -> list[dict]:
        return [self.spec_state(spec) for spec in spec_dirs(self.root)]


def hints(root: Path, ctx: Context, row: dict, phase: str) -> dict:
    spec = row["spec"]
    spec_text = read_text(root / "specs" / spec / "spec.md") or ""
    plan = root / "specs" / spec / "plan.md"
    contracts = root / "specs" / spec / "contracts"
    models: list[str] = []
    for attempt in ctx.state["attempts"]:
        if attempt["model"] not in models:
            models.append(attempt["model"])
    result = {
        "requirements": len(set(re.findall(r"\bFR-\d+\b", spec_text))),
        "user_stories": len(re.findall(r"^#{2,4}\s+User Story\b", spec_text, re.MULTILINE)),
        "plan_bytes": plan.stat().st_size if plan.is_file() else 0,
        "contracts": sum(1 for p in contracts.iterdir() if p.is_file()) if contracts.is_dir() else 0,
        "tasks_total": row["tasks_total"],
        "tasks_open": row["tasks_open"],
        "phase_failures": row["failures"].get(phase, 0),
        "models_used_this_run": models,
    }
    if phase == "check":
        result["check_failures"] = row["failures"].get("check", 0)
    return result


def covers(ctx: Context, rows: list[dict], spec: str, command: str | None) -> list[str]:
    """The spec and the consecutive specs after it that also need a test with the same command (D5)."""
    result = []
    started = False
    for row in rows:
        if row["spec"] == spec:
            started = True
        if not started:
            continue
        if row["next_phase"] != "test" or test_command(ctx.root, row["spec"])[0] != command:
            break
        result.append(row["spec"])
    return result


def launch_recent(state: dict) -> bool:
    launch = state.get("launch")
    return launch is not None and now_ts() - parse_ts(launch["at"]) <= LAUNCH_SECONDS


def attempt_summary(attempt: dict | None, keys: tuple) -> dict | None:
    if attempt is None:
        return None
    return {key: attempt[key] for key in keys}


def blank_next(action: str) -> dict:
    return {key: (action if key == "action" else None) for key in NEXT_KEYS}


def compute_status(root: Path, state: dict, ctx: Context | None = None, own_lock: bool = False) -> dict:
    """The status object (after the prerequisites passed). own_lock: this process holds the lock."""
    ctx = ctx or Context(root, state)
    held = False if own_lock else lock_held(root)
    running = held or launch_recent(state)
    attempts = state["attempts"]
    last = attempts[-1] if attempts else None
    finished = [a for a in attempts if a["outcome"] is not None]
    pending = (not running) and ((last is not None and last["outcome"] is None) or state["driver"] is not None
                                 or state["launch"] is not None)
    dirty = dirty_paths(root) if ctx.git else []
    rows = ctx.specs()
    current = next((row for row in rows if row["state"] != "done"), None)
    running_attempt = None
    if running and attempts:
        driver = state["driver"]
        chosen = None
        if driver is not None:
            chosen = next((a for a in attempts if a["id"] == driver["attempt"]), None)
        if chosen is None:
            open_attempts = [a for a in attempts if a["outcome"] is None]
            chosen = open_attempts[-1] if open_attempts else None
        running_attempt = attempt_summary(chosen, ("spec", "phase", "model", "started_at", "limit", "auto_resume"))
    if running:
        nxt = blank_next("wait")
        if running_attempt is not None:
            nxt["spec"], nxt["phase"] = running_attempt["spec"], running_attempt["phase"]
            nxt["limit"], nxt["auto_resume"] = running_attempt["limit"], running_attempt["auto_resume"]
    elif pending:
        nxt = blank_next("finalize")
        if last is not None:
            nxt["spec"], nxt["phase"] = last["spec"], last["phase"]
    elif current is None:
        nxt = blank_next("none")
    else:
        spec, phase = current["spec"], current["next_phase"]
        nxt = blank_next("run")
        nxt["spec"], nxt["phase"] = spec, phase
        nxt["branch"] = spec if ctx.git else None
        nxt["failures"] = current["failures"]
        if phase == "test":
            nxt["action"] = "test"
            command, _ = test_command(root, spec)
            nxt["test_command"] = command
            nxt["covers"] = covers(ctx, rows, spec, command) if command else [spec]
        else:
            on_phase = ctx.attempts_for(spec, phase)
            last_on_phase = on_phase[-1] if on_phase else None
            if last_on_phase is not None and last_on_phase["outcome"] in RESUMABLE:
                nxt["action"] = "resume"
                nxt["session_id"] = last_on_phase["session_id"]
                nxt["model"] = last_on_phase["model"]
                nxt["last_outcome"] = last_on_phase["outcome"]
                nxt["limit"] = last_on_phase["limit"]
                nxt["auto_resume"] = last_on_phase["auto_resume"]
            nxt["hints"] = hints(root, ctx, current, phase)
    leftovers = False
    if dirty and nxt["action"] in ("resume", "finalize") and last is not None:
        leftovers = last["worktree"] is not None and last["worktree"] == worktree_fingerprint(root)
    return {
        "speckit": "ok",
        "missing": [],
        "claude": "ok",
        "git": ctx.git,
        "branch": current_branch(root) if ctx.git else None,
        "own_dir": own_dir_state(root),
        "running": running,
        "running_attempt": running_attempt,
        "driver": state["driver"],
        "last_attempt": attempt_summary(finished[-1] if finished else None,
                                        ("spec", "phase", "outcome", "auto", "limit", "auto_resume", "ended_at")),
        "pending_finalize": pending,
        "dirty": [clean_path(p) for p in dirty],
        "leftovers": leftovers,
        "specs": rows,
        "next": nxt,
    }


# ----------------------------------------------------------- prerequisites


def speckit_check(root: Path) -> tuple[str, list[str]]:
    if not (root / ".specify").is_dir():
        return "missing", []
    missing = [name for name in REQUIRED_SKILLS if not (root / ".claude" / "skills" / name / "SKILL.md").is_file()]
    return ("incomplete", missing) if missing else ("ok", [])


def prerequisites(root: Path, need_specs: bool = False) -> dict:
    """Check in the documented order; returns the loaded records. Raises Failure."""
    speckit, missing = speckit_check(root)
    if speckit == "missing":
        raise fail("speckit-missing", speckit="missing", missing=[])
    if speckit == "incomplete":
        raise fail("speckit-incomplete", ", ".join(missing), speckit="incomplete", missing=missing)
    if need_specs and not spec_dirs(root):
        raise fail("no-specs")
    if claude_command() is None:
        raise fail("claude-missing", claude="missing")
    return read_records(root)


def read_records(root: Path) -> dict:
    if own_dir_state(root) == "conflict":
        raise fail("conflict")
    try:
        return current_state(root)
    except Unreadable as error:
        raise fail("state-unreadable", error.path, detail=error.path)


# ------------------------------------------------------------- work brief

BRIEF_COMMON = """\
You are a child session started by sdd-drive. Work without a person: nobody will answer questions or approve anything.

Project root: . (the current directory)
Spec directory: {spec_path}
Phase: {phase}
Branch: {branch}

## Goal

Do only the {phase} phase of the spec in {spec_path}, and nothing for any other spec or phase.
Use the Skill tool to invoke the `{skill}` skill for this spec; it is the only way to do this phase.
You MUST NOT write or edit the artifacts of `{skill}` by hand instead of running the skill.

## Decisions

- Do not ask questions and do not wait for approval; there is nobody to answer.
- Make technical decisions yourself from the constitution (.specify/memory/constitution.md), the spec and the existing
  design, and write down the reason for each decision in the documents of this spec.
- If the requirements contradict each other or are not enough to decide, stop and report status failed with
  failure kind "requirements". You MUST NOT modify spec.md or the constitution to resolve it.

## Files you must not change

- You MUST NOT modify spec.md of any spec or .specify/memory/constitution.md.
- You MUST NOT modify the Spec Kit templates (.specify/templates/), scripts (.specify/scripts/) or any `speckit-*` skill
  under .claude/skills/.
- You MUST NOT modify the folders of other specs under specs/, or anything in .specify/sdd-drive/.
"""

BRIEF_PHASE = {
    "plan": """\
## This phase

- Write the test command of this spec on the **Testing**: line of plan.md, inside the first backtick span of that
  line, e.g. **Testing**: `uv run --with pytest pytest`. It must run as it is from the project root and be written
  the same way on Windows and Linux.
""",
    "tasks": """\
## This phase

- Write every task as a task line in the form `- [ ] T001 Description with the file path`.
- Items that need the maintainer or a push to finish (manual acceptance, checking CI after a push) go in the Notes
  section of tasks.md, never as task lines.
""",
    "implement": """\
## This phase

- Do only the unchecked tasks in {spec_path}/tasks.md; tasks already checked are done.
- Check a task off as soon as it is done.
- You MUST NOT delete, rewrite or merge tasks.
- A task you cannot do (for example it needs the maintainer or a push): leave it unchecked and report status failed
  with failure kind "blocked-task", listing the task IDs in "tasks".
- Before you finish, run the test command and make it pass: {test_command}
- New tests must not depend on the order in which tests run; follow the project's test conventions.
""",
    "check": """\
## This phase

- The only write allowed is the Convergence section that `speckit-converge` appends at the end of {spec_path}/tasks.md.
- You MUST NOT modify code, tests, plan.md, spec.md or any other file.
- You MUST NOT check, rewrite, delete or renumber existing tasks.
- You MUST NOT fix the problems you find yourself; only report them through the appended tasks.
""",
}

BRIEF_GIT = {
    "plan": None, "tasks": None, "implement": None,
    "check": """\
## Git

- When speckit-converge appended tasks, commit {spec_path}/tasks.md in one commit that holds only that file.
- When nothing was found, you MUST NOT create any commit or change any file.
- Leave no uncommitted changes when you finish.
- You MUST NOT push, switch or create branches, amend, rebase, reset, merge, stash or clean.
""",
}

BRIEF_GIT_DEFAULT = """\
## Git

- Commit to the current branch each time a document or a group of tasks is done; follow the commit message rules of
  the project's and the user's CLAUDE.md.
- Leave no uncommitted changes when you finish.
- You MUST NOT push, switch or create branches, amend, rebase, reset, merge, stash or clean.
"""

BRIEF_NO_GIT = """\
## Git

- This project is not a git repository: do not commit.
"""

BRIEF_RESUME = """\
## Resuming

This continues an earlier session of this phase. First check the current state of the files again, then continue from
the part that is not finished; do not redo what is already done.
"""

BRIEF_END = """\
## Secrets

Never write secret values (keys, tokens, passwords) into files, commits or the report.

## Report

Finish with the structured output: "status" (completed or failed), "summary" (what you did and which commits you
made), and "failure" ({{"kind", "step", "reason"}}) when the status is failed.{check_report}
"""


def brief_text(root: Path, spec: str, phase: str, resume: bool = False) -> str:
    git = is_git(root)
    command, _ = test_command(root, spec)
    values = {
        "spec_path": f"specs/{spec}",
        "phase": phase,
        "branch": spec if git else "(not a git repository)",
        "skill": PHASE_SKILLS[phase],
        "test_command": f"`{command}`" if command else "(plan.md has no test command; report failed, kind tooling)",
    }
    parts = [BRIEF_COMMON.format(**values), BRIEF_PHASE[phase].format(**values)]
    if not git:
        parts.append(BRIEF_NO_GIT)
    else:
        parts.append((BRIEF_GIT[phase] or BRIEF_GIT_DEFAULT).format(**values))
    if resume:
        parts.append(BRIEF_RESUME)
    check_report = (' Also report "convergence": "converged" when nothing was found, or "tasks-appended" when tasks'
                    " were appended." if phase == "check" else "")
    parts.append(BRIEF_END.format(check_report=check_report))
    return "\n".join(parts)


# -------------------------------------------------------------- arguments

SPEC_ARGS = {
    "status": ((), ()),
    "brief": (("--spec", "--phase"), ()),
    "run": (("--spec", "--phase", "--model", "--reason"), ()),
    "watch": ((), ("--minutes",)),
    "cancel": ((), ()),
    "test": (("--spec",), ()),
    "finalize": ((), ()),
    "clear": ((), ()),
    "_drive": (("--token",), ()),
}
FLAGS = {"run": ("--resume", "--fresh")}


def parse_args(argv: list[str]) -> tuple[str, dict]:
    if not argv or argv[0] not in SPEC_ARGS:
        raise Usage
    command, rest = argv[0], argv[1:]
    required, optional = SPEC_ARGS[command]
    flags = FLAGS.get(command, ())
    options: dict = {flag: False for flag in flags}
    seen: set[str] = set()
    index = 0
    while index < len(rest):
        name = rest[index]
        if name in seen:
            raise Usage
        seen.add(name)
        if name in flags:
            options[name] = True
            index += 1
        elif name in required or name in optional:
            if index + 1 >= len(rest):
                raise Usage
            options[name] = rest[index + 1]
            index += 2
        else:
            raise Usage
    if any(name not in options for name in required):
        raise Usage
    if "--phase" in options and options["--phase"] not in PHASES:
        raise Usage
    if "--spec" in options and not spec_name_ok(options["--spec"]):
        raise Usage
    if "--model" in options and not MODEL.match(options["--model"]):
        raise Usage
    if "--reason" in options:
        reason = options["--reason"]
        if not reason.strip() or len(reason) > 300 or "\n" in reason or "\r" in reason:
            raise Usage
    if "--minutes" in options:
        try:
            minutes = int(options["--minutes"])
        except ValueError:
            raise Usage
        if not 1 <= minutes <= 115:
            raise Usage
        options["--minutes"] = minutes
    if "--token" in options and not UUID_FORM.match(options["--token"]):
        raise Usage
    return command, options


# --------------------------------------------------------------------- Io


class Io:
    def __init__(self, root: Path, stdout, stderr):
        self.root = root
        self.stdout = stdout
        self.stderr = stderr

    def emit(self, data: dict, code: int = EXIT_OK) -> int:
        self.stdout.write(dumps(data))
        self.stdout.flush()
        if "error" in data:
            self.stderr.write((data["error"] + "\n").encode("utf-8"))
            self.stderr.flush()
        return code

    def text(self, text: str) -> int:
        self.stdout.write(text.encode("utf-8"))
        self.stdout.flush()
        return EXIT_OK

    def failure(self, error: Failure, base: dict | None = None) -> int:
        data = dict(base or {})
        data.update(error.fields)
        data["error"] = error.message
        data["reason"] = error.reason
        return self.emit(data, error.code)


# ------------------------------------------------------------------ status


def command_status(io: Io, options: dict) -> int:
    root = io.root
    base = {key: None for key in STATUS_KEYS}
    speckit, missing = speckit_check(root)
    base["speckit"], base["missing"] = speckit, missing
    try:
        state = prerequisites(root, need_specs=True)
    except Failure as error:
        base["claude"] = "missing" if error.reason == "claude-missing" else (
            "ok" if error.reason in ("conflict", "state-unreadable") else None)
        if error.reason in ("conflict", "state-unreadable"):
            base["own_dir"] = own_dir_state(root)
        if error.reason == "state-unreadable":
            base["detail"] = error.fields.get("detail")
        error.fields.pop("speckit", None)
        error.fields.pop("missing", None)
        error.fields.pop("detail", None)
        error.fields.pop("claude", None)
        return io.failure(error, base)
    return io.emit(compute_status(root, state))


# ------------------------------------------------------------------- brief


def command_brief(io: Io, options: dict) -> int:
    spec = options["--spec"]
    if spec not in spec_dirs(io.root):
        raise Usage
    return io.text(brief_text(io.root, spec, options["--phase"]))


# --------------------------------------------------------------------- run


def new_attempt(state: dict, spec: str, phase: str, session_id: str, resume: bool, model: str, reason: str,
                auto: bool) -> dict:
    last_id = state["attempts"][-1]["id"] if state["attempts"] else 0
    attempt = {key: None for key in ATTEMPT_KEYS}
    attempt.update({
        "id": last_id + 1, "spec": spec, "phase": phase, "session_id": session_id, "resume": resume, "model": model,
        "model_used": [], "reason": reason, "started_at": utc_now(), "auto": auto, "permission_denials": [],
    })
    state["attempts"].append(attempt)
    return attempt


def check_ready(root: Path, state: dict, ctx: Context) -> dict:
    """The status after pending-finalize and dirty checks (shared by run and test)."""
    status = compute_status(root, state, ctx, own_lock=True)
    if status["running"] and status["next"]["action"] == "wait":
        raise fail("running")
    if status["pending_finalize"]:
        raise fail("pending-finalize")
    return status


def check_dirty(status: dict) -> None:
    if status["dirty"] and not status["leftovers"]:
        raise fail("dirty", dirty=status["dirty"])


def command_run(io: Io, options: dict) -> int:
    root = io.root
    spec, phase = options["--spec"], options["--phase"]
    model, reason = options["--model"], options["--reason"]
    resume, fresh = options["--resume"], options["--fresh"]
    if secret(reason):
        raise fail("secret")
    state = prerequisites(root)
    lock = Lock(root)
    if launch_recent(state) or not lock.try_acquire():
        raise fail("running")
    try:
        state = read_records(root)
        if launch_recent(state):
            raise fail("running")
        ctx = Context(root, state)
        status = check_ready(root, state, ctx)
        nxt = status["next"]
        label = f"{spec} {phase}"
        if nxt["action"] not in ("run", "resume") or nxt["spec"] != spec or nxt["phase"] != phase:
            raise fail("not-next", label)
        if nxt["action"] == "resume" and not resume:
            raise fail("not-next", label)
        if nxt["action"] != "resume" and resume:
            raise fail("not-next", label)
        if fresh and not resume:
            raise fail("not-next", label)
        check_dirty(status)
        if ctx.git:
            prepare_branch(root, spec)
        set_feature_directory(root, spec)
        cancel = own_dir(root) / CANCEL_NAME
        if cancel.exists():
            cancel.unlink()
        continuing = resume and not fresh
        session_id = nxt["session_id"] if continuing else str(uuid.uuid4())
        attempt = new_attempt(state, spec, phase, session_id, continuing, model, reason, auto=False)
        token = str(uuid.uuid4())
        state["launch"] = {"token": token, "at": utc_now()}
        save_state(root, state)
        first_id = attempt["id"]
        launched = start_driver(root, token)
        if not launched:
            state = load_state(root)
            state["launch"] = None
            for item in state["attempts"]:
                if item["id"] == first_id:
                    item["outcome"] = "launch-failed"
                    item["ended_at"] = utc_now()
                    item["detail"] = make_detail("launch", text="the driver process could not be started")
            save_state(root, state)
    finally:
        lock.release()
    return watch_loop(io, options.get("--minutes", DEFAULT_MINUTES), first_id=first_id)


DRIVER_STARTER = r"""
import os, subprocess, sys
kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
if os.name == "nt":
    flags = 0x00000008 | 0x00000200
    try:
        subprocess.Popen(sys.argv[1:], creationflags=flags | 0x01000000, **kwargs)
    except OSError:
        subprocess.Popen(sys.argv[1:], creationflags=flags, **kwargs)
else:
    subprocess.Popen(sys.argv[1:], start_new_session=True, **kwargs)
"""


def start_driver(root: Path, token: str) -> bool:
    """Two-step start: a short-lived middle process starts the driver and exits, so the driver is detached."""
    args = [sys.executable, "-c", DRIVER_STARTER, sys.executable, os.path.abspath(__file__), "_drive", "--token", token]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "cwd": root}
    try:
        if WINDOWS:
            flags = 0x00000008 | 0x00000200
            try:
                middle = subprocess.Popen(args, creationflags=flags | 0x01000000, **kwargs)
            except OSError:
                middle = subprocess.Popen(args, creationflags=flags, **kwargs)
        else:
            middle = subprocess.Popen(args, start_new_session=True, **kwargs)
        return middle.wait(timeout=60) == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ------------------------------------------------------------------ driver


def update_state(root: Path, change) -> dict:
    state = load_state(root)
    change(state)
    save_state(root, state)
    return state


def find_attempt(state: dict, attempt_id: int) -> dict:
    return next(a for a in state["attempts"] if a["id"] == attempt_id)


def command_drive(io: Io, options: dict) -> int:
    root = io.root
    token = options["--token"]
    lock = Lock(root)
    if not lock.acquire(LAUNCH_SECONDS):
        return EXIT_FAILED
    try:
        state = load_state(root)
        if state is None or state["launch"] is None or state["launch"]["token"] != token:
            return EXIT_FAILED
        attempt_id = state["attempts"][-1]["id"]
        state["launch"] = None
        state["driver"] = {"token": token, "pid": os.getpid(), "phase": "running", "attempt": attempt_id,
                           "waiting_until": None, "started_at": utc_now()}
        save_state(root, state)
        drive_loop(root, attempt_id)
    finally:
        try:
            state = load_state(root)
            if state is not None and state["driver"] is not None and state["driver"]["token"] == token:
                state["driver"] = None
                save_state(root, state)
        finally:
            lock.release()
    return EXIT_OK


def drive_loop(root: Path, attempt_id: int) -> None:
    while True:
        run_child(root, attempt_id)
        state = load_state(root)
        attempt = find_attempt(state, attempt_id)
        if attempt["outcome"] != "usage-limit":
            return
        limit = attempt["limit"]
        if not limit["waitable"]:
            update_state(root, lambda s: find_attempt(s, attempt_id).update(auto_resume="not-waitable"))
            return
        if attempt["auto"]:
            update_state(root, lambda s: find_attempt(s, attempt_id).update(auto_resume="already-auto"))
            return
        until = max(parse_ts(limit["resets_at"]), now_ts()) + margin_seconds()
        until_text = format_ts(until + 0.999)

        def start_wait(s):
            find_attempt(s, attempt_id)["auto_resume"] = "waiting"
            s["driver"]["phase"] = "waiting"
            s["driver"]["waiting_until"] = until_text

        update_state(root, start_wait)
        cancel = own_dir(root) / CANCEL_NAME
        outcome = None
        while True:
            if cancel.exists():
                outcome = "cancelled"
                break
            if now_ts() >= parse_ts(until_text):
                break
            time.sleep(min(poll_seconds(), max(0.01, parse_ts(until_text) - now_ts())))
        if outcome is None and worktree_fingerprint(root) != attempt["worktree"]:
            outcome = "skipped-changed"
        if outcome is None and cancel.exists():
            outcome = "cancelled"
        if outcome is not None:
            if outcome == "cancelled":
                try:
                    cancel.unlink()
                except OSError:
                    pass

            def stop_wait(s, outcome=outcome):
                find_attempt(s, attempt_id)["auto_resume"] = outcome
                s["driver"]["phase"] = "running"
                s["driver"]["waiting_until"] = None

            update_state(root, stop_wait)
            return
        holder: dict = {}

        def resume(s):
            old = find_attempt(s, attempt_id)
            old["auto_resume"] = "started"
            fresh = new_attempt(s, old["spec"], old["phase"], old["session_id"], True, old["model"], AUTO_REASON, True)
            s["driver"]["phase"] = "resuming"
            s["driver"]["waiting_until"] = None
            s["driver"]["attempt"] = fresh["id"]
            holder["id"] = fresh["id"]

        update_state(root, resume)
        attempt_id = holder["id"]


def child_args(command: list[str], attempt: dict) -> list[str]:
    session = ["--resume", attempt["session_id"]] if attempt["resume"] else ["--session-id", attempt["session_id"]]
    return [
        *command, "-p", "--output-format", "stream-json", "--verbose", "--model", attempt["model"], *session,
        "--json-schema", json.dumps(REPORT_SCHEMA, separators=(",", ":")),
        "--permission-mode", "acceptEdits", "--permission-prompts", "none",
        "--allowedTools", "Bash", "Skill", "--disallowedTools", "AskUserQuestion", "Bash(git push*)",
    ]


def read_stream(stream) -> tuple[dict | None, list[dict]]:
    """Keep only the result object and the rejected rate-limit information."""
    result = None
    limits: list[dict] = []
    for raw in stream:
        try:
            item = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "rate_limit_event":
            info = item.get("rate_limit_info")
            if isinstance(info, dict) and info.get("status") == "rejected":
                limits.append(info)
        elif kind == "assistant":
            for holder in (item, item.get("message") if isinstance(item.get("message"), dict) else {}):
                params = holder.get("api_error_params")
                if isinstance(params, dict) and isinstance(params.get("rate_limit_info"), dict):
                    limits.append(dict(params["rate_limit_info"], status="rejected"))
        elif kind == "result":
            result = item
    return result, limits


def compute_limit(infos: list[dict], started_at: str) -> dict:
    """D17 / E10: waitable only when a rejected time window has a reset time; anything unclear is not waitable."""
    types: list[str] = []
    resets: list[float] = []
    veto = False
    overage_status = None

    def add(kind):
        name = kind if kind in LIMIT_TYPES else "unknown"
        if name not in types:
            types.append(name)

    def number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    for info in infos:
        if info.get("overageStatus") in OVERAGE_STATUSES:
            overage_status = info["overageStatus"]
        if info.get("dailyCapPaused") is True:
            veto = True
        kind = info.get("rateLimitType")
        windows = info.get("unifiedWindows")
        rejected = []
        if isinstance(windows, dict):
            rejected = [(n, w) for n, w in windows.items() if isinstance(w, dict) and w.get("status") == "rejected"]
        if rejected:
            if isinstance(kind, str) and kind not in WINDOW_TYPES:
                add(kind)
            for name, window in rejected:
                add(name)
                if name in WINDOW_TYPES and number(window.get("resetsAt")):
                    resets.append(float(window["resetsAt"]))
                else:
                    veto = True
        elif isinstance(kind, str):
            add(kind)
            if kind in WINDOW_TYPES and number(info.get("resetsAt")):
                resets.append(float(info["resetsAt"]))
        else:
            add("unknown")
    if not types:
        types = ["unknown"]
    types.sort(key=LIMIT_TYPES.index)
    waitable = bool(resets) and not veto
    resets_at = None
    if waitable:
        latest = max(resets)
        if latest < parse_ts(started_at):
            waitable = False
        else:
            resets_at = format_ts(latest)
    return {"waitable": waitable, "types": types, "resets_at": resets_at, "overage_status": overage_status}


def denials(result: dict) -> list[str]:
    names: list[str] = []
    for item in result.get("permission_denials") or []:
        name = item.get("tool_name") if isinstance(item, dict) else None
        if isinstance(name, str) and TOOL_NAME.match(name) and name not in names:
            names.append(name)
    return names


def run_child(root: Path, attempt_id: int) -> None:
    state = load_state(root)
    attempt = find_attempt(state, attempt_id)
    spec, phase = attempt["spec"], attempt["phase"]
    git = is_git(root)
    tasks_file = root / "specs" / spec / "tasks.md"
    before = {
        "protected": protected_hashes(root),
        "refs": remote_refs(root) if git else "",
        "tasks": read_text(tasks_file) if phase == "check" else None,
        "head": head(root) if git else None,
        "tree": tree_hashes(root, git) if phase == "check" else None,
    }
    earlier = [a for a in state["attempts"] if a["spec"] == spec and a["phase"] == phase and a["id"] < attempt_id]
    continuing = attempt["resume"] or bool(earlier and earlier[-1]["outcome"] in RESUMABLE)  # --resume or --fresh
    prompt = brief_text(root, spec, phase, resume=continuing)
    command = claude_command() or ["claude"]
    record: dict = {}
    try:
        kwargs: dict = {"cwd": root, "stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL}
        if WINDOWS:
            kwargs["creationflags"] = NO_WINDOW
        child = subprocess.Popen(child_args(command, attempt), **kwargs)
    except OSError as error:
        record = {"outcome": "launch-failed", "detail": make_detail("launch", text=str(error.strerror or error))}
    else:
        try:
            child.stdin.write(prompt.encode("utf-8"))
            child.stdin.close()
        except OSError:
            pass
        result, limits = read_stream(child.stdout)
        child.wait()
        record = classify(root, attempt, result, limits, child.returncode, before, git)
    record.setdefault("worktree", worktree_fingerprint(root))
    record.setdefault("tasks_hash", tasks_hash(root, spec))

    def write(s):
        target = find_attempt(s, attempt_id)
        target.update(record)
        target["ended_at"] = utc_now()
        apply_secrets(target)

    update_state(root, write)


def classify(root: Path, attempt: dict, result: dict | None, limits: list[dict], code: int, before: dict,
             git: bool) -> dict:
    """D4: the outcome of one child session, then the checks of D7, D9, D10 and D22."""
    resume = attempt["resume"]
    record: dict = {}
    if isinstance(result, dict):
        used = result.get("modelUsage")
        if isinstance(used, dict):
            record["model_used"] = [m for m in used if isinstance(m, str) and MODEL.match(m)]
        record["permission_denials"] = denials(result)
    if result is None:
        record["outcome"] = "interrupted"
        record["detail"] = make_detail("resume-failed" if resume and code != 0 else "no-result")
        return record
    text = result.get("result") if isinstance(result.get("result"), str) else None
    if result.get("is_error") is True:
        if resume and result.get("num_turns") == 0:
            record["outcome"] = "api-error"
            record["detail"] = make_detail("resume-failed", text=text)
        elif result.get("api_error_status") == 429 or (text and USAGE_TEXT.search(text)):
            record["outcome"] = "usage-limit"
            record["detail"] = make_detail("usage-limit", text=text)
            record["limit"] = compute_limit(limits, attempt["started_at"])
        else:
            record["outcome"] = "api-error"
            subtype = result.get("subtype")
            record["detail"] = make_detail("api-error", text=text or (subtype if isinstance(subtype, str) else None))
        return record
    report = result.get("structured_output")
    if not report_valid(report):
        record["outcome"] = "interrupted"
        record["detail"] = make_detail("no-report")
        return record
    record["report"] = report
    if report["status"] == "failed":
        record["outcome"] = "failed"
        record["detail"] = make_detail("child-failed")
        return record
    if attempt["phase"] == "check":
        record.update(verify_check(root, attempt, report, before, git))
    else:
        record.update(verify_phase(root, attempt, before, git))
    return record


def recorded_task_ids(root: Path, spec: str) -> list[str] | None:
    state = load_state(root)
    ids = None
    for attempt in state["attempts"]:
        if attempt["spec"] == spec and attempt["task_ids"] is not None:
            ids = attempt["task_ids"]
    return ids


def verify_phase(root: Path, attempt: dict, before: dict, git: bool) -> dict:
    spec, phase = attempt["spec"], attempt["phase"]
    code, paths = None, []
    if phase == "plan" and not plan_generated(root, spec):
        code = "plan-missing"
    elif phase == "tasks" and not tasks_generated(root, spec):
        code = "tasks-missing"
    elif phase == "implement":
        total, open_, ids = task_counts(root, spec)
        recorded = recorded_task_ids(root, spec) or []
        if not tasks_generated(root, spec) or open_:
            code = "tasks-unfinished"
        elif any(task_id not in ids for task_id in recorded):
            code = "tasks-removed"
            paths = [f"specs/{spec}/tasks.md"]
    if code is None:
        changed = changed_keys(before["protected"], protected_hashes(root))
        if changed:
            code, paths = "protected-changed", changed
    if code is None and git and remote_refs(root) != before["refs"]:
        code = "pushed"
    if code is None and git:
        dirty = dirty_paths(root)
        if dirty:
            code, paths = "uncommitted", dirty
    if code is not None:
        return {"outcome": "verify-failed", "detail": make_detail(code, paths)}
    record: dict = {"outcome": "succeeded"}
    if phase == "tasks":
        record["task_ids"] = task_counts(root, spec)[2]
    return record


CONVERGENCE_HEADING = re.compile(r"^## Phase \d+: Convergence\s*$")
OPEN_TASK = re.compile(r"^- \[ \] (T\d{3,})\b")


def appended_ids(old: str, new: str) -> list[str] | None:
    """The IDs of a valid Convergence section appended to old, or None when new is not old plus such a section."""
    if not new.startswith(old) or new == old:
        return None
    suffix = new[len(old):]
    lines = suffix.split("\n")
    if old and not old.endswith("\n"):
        if lines[0] != "":
            return None
        lines = lines[1:]
    old_ids = [int(task_id[1:]) for task_id, _ in task_entries(old)]
    top = max(old_ids) if old_ids else 0
    headings = 0
    ids: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if CONVERGENCE_HEADING.match(line):
            if headings or ids:
                return None
            headings += 1
            continue
        match = OPEN_TASK.match(line)
        if match:
            if not headings:
                return None
            task_id = match.group(1)
            if int(task_id[1:]) <= top or task_id in ids:
                return None
            ids.append(task_id)
            continue
        if line[:1] in (" ", "\t") and ids:
            continue
        return None
    if headings != 1 or not ids:
        return None
    return ids


def verify_check(root: Path, attempt: dict, report: dict, before: dict, git: bool) -> dict:
    spec = attempt["spec"]
    tasks_rel = f"specs/{spec}/tasks.md"
    old = before["tasks"] or ""
    new = read_text(root / tasks_rel) or ""
    protected = changed_keys(before["protected"], protected_hashes(root))
    tree_changed = changed_keys(before["tree"], tree_hashes(root, git))
    other = [p for p in tree_changed if p != tasks_rel and p not in protected]
    said = report.get("convergence")

    def failed(code, paths=()):
        return {"outcome": "verify-failed", "detail": make_detail(code, list(paths)), "convergence": None}

    if protected:
        return failed("protected-changed", protected)
    if other:
        return failed("check-touched-files", other)
    ids = None
    if new != old:
        ids = appended_ids(old, new)
        if ids is None:
            return failed("check-rewrote-tasks", [tasks_rel])
    if git and remote_refs(root) != before["refs"]:
        return failed("pushed")
    if git:
        dirty = dirty_paths(root)
        if dirty:
            return failed("uncommitted", dirty)
    if ids is None:
        if git and head(root) != before["head"]:
            return failed("check-touched-files")
        if said == "tasks-appended":
            return failed("check-no-tasks")
        return {"outcome": "succeeded", "convergence": "converged"}
    original = [task_id for task_id, _ in task_entries(old)]
    record = {"outcome": "gaps-found", "convergence": "tasks-appended", "appended": ids, "task_ids": original + ids}
    record["detail"] = make_detail("report-mismatch") if said == "converged" else None
    return record


# ------------------------------------------------------------------- watch


def chain(state: dict, first_id: int | None = None) -> list[dict]:
    """The attempts of one driver: from first_id, or the last attempt and the ones it automatically resumed."""
    attempts = state["attempts"]
    if not attempts:
        return []
    if first_id is not None:
        return [a for a in attempts if a["id"] >= first_id]
    index = len(attempts) - 1
    while index > 0 and attempts[index]["auto"]:
        index -= 1
    return attempts[index:]


FINDING = re.compile(r"^- \[ \] (T\d{3,})\s+(.*)$")
FINDING_TAIL = re.compile(r"^(.*?)\s+per\s+(.+?)\s+\((missing|partial|contradicts|unrequested)\)\s*$")


def findings(root: Path, attempt: dict) -> tuple[list[dict] | None, int | None]:
    if attempt["outcome"] != "gaps-found" or not attempt["appended"]:
        return None, None
    text = read_text(root / "specs" / attempt["spec"] / "tasks.md") or ""
    wanted = set(attempt["appended"])
    items = []
    for line in text.split("\n"):
        match = FINDING.match(line)
        if match and match.group(1) in wanted:
            body = match.group(2).strip()
            tail = FINDING_TAIL.match(body)
            if tail:
                item = {"id": match.group(1), "text": tail.group(1), "source_ref": tail.group(2), "gap_type": tail.group(3)}
            else:
                item = {"id": match.group(1), "text": body, "source_ref": None, "gap_type": None}
            item["text"] = clean_text(item["text"][:300])
            if item["source_ref"] is not None:
                item["source_ref"] = clean_text(item["source_ref"][:300])
            items.append(item)
    return items[:50], len(items)


def attempt_view(root: Path, attempt: dict) -> dict:
    report = attempt["report"] or {}
    failure = None
    if attempt["outcome"] == "failed" and "failure" in report:
        failure = dict(report["failure"])
        failure["tasks"] = list(report.get("tasks") or [])
    duration = None
    if attempt["ended_at"]:
        duration = int(parse_ts(attempt["ended_at"]) - parse_ts(attempt["started_at"]))
    items, total = findings(root, attempt)
    detail = attempt["detail"]
    return {
        "spec": attempt["spec"],
        "phase": attempt["phase"],
        "outcome": attempt["outcome"],
        "auto": attempt["auto"],
        "counts_as_failure": attempt["outcome"] in FAILURE_OUTCOMES,
        "model": attempt["model"],
        "model_used": attempt["model_used"],
        "reason": attempt["reason"],
        "session_id": attempt["session_id"],
        "resume": attempt["resume"],
        "resume_failed": detail is not None and detail["code"] == "resume-failed",
        "duration_seconds": duration,
        "summary": report.get("summary"),
        "failure": failure,
        "detail": detail,
        "limit": attempt["limit"],
        "convergence": attempt["convergence"],
        "findings": items,
        "findings_total": total,
        "auto_resume": attempt["auto_resume"],
        "permission_denials": attempt["permission_denials"],
    }


def watch_output(root: Path, state: dict, status: str, attempts: list[dict], waiting_until: str | None) -> dict:
    spec = attempts[-1]["spec"] if attempts else None
    state_after, failures = None, {}
    if spec is not None and (root / "specs" / spec).is_dir():
        row = Context(root, state).spec_state(spec)
        state_after = {key: row[key] for key in ("state", "next_phase", "tasks_total", "tasks_open")}
        failures = row["failures"]
    return {
        "status": status,
        "attempts": [attempt_view(root, a) for a in attempts],
        "waiting_until": waiting_until,
        "state_after": state_after,
        "failures": failures,
    }


def watch_limit_seconds(minutes: int) -> float:
    test = timing()
    if test:
        return float(test["watch_seconds"])
    return minutes * 60.0


def command_watch(io: Io, options: dict) -> int:
    read_records(io.root)
    return watch_loop(io, options.get("--minutes", DEFAULT_MINUTES))


def watch_loop(io: Io, minutes: int, first_id: int | None = None) -> int:
    """Wait for the driver to finish, to start waiting during this watch, or for the time limit (read only)."""
    root = io.root
    deadline = time.monotonic() + watch_limit_seconds(minutes)
    interval = min(2.0, max(0.05, poll_seconds() / 4))
    state = read_records(root)
    driver = state["driver"]
    reported_wait = (driver["attempt"], driver["waiting_until"]) if driver and driver["phase"] == "waiting" else None
    if first_id is None and driver is None and state["launch"] is None and not lock_held(root):
        attempts = chain(state)
        if not attempts:
            raise fail("no-driver")
        return io.emit(watch_output(root, state, "finished", attempts, None))
    while True:
        state = read_records(root)
        attempts = chain(state, first_id)
        driver = state["driver"]
        launch = state["launch"]
        held = lock_held(root)
        if driver is None and launch is None and not held:
            return io.emit(watch_output(root, state, "finished", attempts, None))
        if launch is not None and not held and not launch_recent(state):
            return io.emit(watch_output(root, state, "launch-failed", attempts, None))
        if driver is not None and not held and launch is None:
            # The driver disappeared without clearing its record; status will ask for finalize.
            return io.emit(watch_output(root, state, "finished", attempts, None))
        if driver is not None and driver["phase"] == "waiting":
            key = (driver["attempt"], driver["waiting_until"])
            if key != reported_wait:
                return io.emit(watch_output(root, state, "waiting", attempts, driver["waiting_until"]))
        if time.monotonic() >= deadline:
            if driver is not None and driver["phase"] == "waiting":
                return io.emit(watch_output(root, state, "waiting", attempts, driver["waiting_until"]))
            return io.emit(watch_output(root, state, "running", attempts, None))
        time.sleep(interval)


# ------------------------------------------------------------------ cancel


def command_cancel(io: Io, options: dict) -> int:
    state = read_records(io.root)
    driver = state["driver"]
    if driver is None or driver["phase"] != "waiting" or not lock_held(io.root):
        raise fail("not-waiting")
    path = own_dir(io.root) / CANCEL_NAME
    if not path.exists():
        atomic_write(path, b"")
    return io.emit({"cancel_requested": True, "waiting_until": driver["waiting_until"]})


# -------------------------------------------------------------------- test


def run_shell(root: Path, command: str) -> tuple[int, str]:
    kwargs: dict = {"cwd": root, "stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT,
                    "shell": True}
    if WINDOWS:
        kwargs["creationflags"] = NO_WINDOW
    done = subprocess.run(command, **kwargs)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def command_test(io: Io, options: dict) -> int:
    root = io.root
    spec = options["--spec"]
    state = prerequisites(root)
    lock = Lock(root)
    if launch_recent(state) or not lock.try_acquire():
        raise fail("running")
    try:
        state = read_records(root)
        if launch_recent(state):
            raise fail("running")
        ctx = Context(root, state)
        status = check_ready(root, state, ctx)
        nxt = status["next"]
        if nxt["action"] != "test" or nxt["spec"] != spec:
            raise fail("not-next", f"{spec} test")
        check_dirty(status)
        command, problem = test_command(root, spec)
        if command is None:
            detail = {"missing": "no backtick command on the **Testing**: line",
                      "placeholder": "the **Testing**: command is a placeholder",
                      "secret": "the **Testing**: command looks like a secret and was not run"}[problem]
            raise fail("no-test-command", spec, detail=detail)
        started = now_ts()
        exit_code, output = run_shell(root, command)
        duration = int(now_ts() - started)
        state = read_records(root)
        ctx = Context(root, state)
        current_head = head(root) if ctx.git else None
        targets = nxt["covers"] if exit_code == 0 else [spec]
        for name in targets:
            state["tests"].append({"spec": name, "tasks_hash": tasks_hash(root, name), "command": command,
                                   "exit_code": exit_code, "head": current_head, "at": utc_now()})
        save_state(root, state)
    finally:
        lock.release()
    lines = output.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    tail = [SECRET_LINE if secret(line) else line for line in lines[-40:]]
    return io.emit({"spec": spec, "command": command, "exit_code": exit_code, "passed": exit_code == 0,
                    "covers": targets if exit_code == 0 else [spec], "duration_seconds": duration,
                    "output_tail": tail})


# ---------------------------------------------------------------- finalize


def command_finalize(io: Io, options: dict) -> int:
    root = io.root
    state = read_records(root)
    lock = Lock(root)
    if launch_recent(state) or not lock.try_acquire():
        raise fail("running")
    try:
        state = read_records(root)
        if launch_recent(state):
            raise fail("running")
        attempts = state["attempts"]
        last = attempts[-1] if attempts else None
        if not ((last is not None and last["outcome"] is None) or state["driver"] is not None
                or state["launch"] is not None):
            raise fail("nothing-to-finalize")
        if last is not None and last["outcome"] is None:
            last["outcome"] = "interrupted"
            last["ended_at"] = utc_now()
            last["detail"] = make_detail("no-result")
            last["worktree"] = worktree_fingerprint(root)
            last["tasks_hash"] = tasks_hash(root, last["spec"])
        for attempt in attempts:
            if attempt["auto_resume"] == "waiting":
                attempt["auto_resume"] = "lost"
        state["launch"] = None
        state["driver"] = None
        save_state(root, state)
    finally:
        lock.release()
    output = {"spec": None, "phase": None, "model": None, "started_at": None, "outcome": None, "auto_resume": None,
              "state_after": None}
    if last is not None:
        output.update({key: last[key] for key in ("spec", "phase", "model", "started_at", "outcome", "auto_resume")})
        if (root / "specs" / last["spec"]).is_dir():
            row = Context(root, state).spec_state(last["spec"])
            output["state_after"] = {key: row[key] for key in ("state", "next_phase", "tasks_total", "tasks_open")}
    return io.emit(output)


# ------------------------------------------------------------------- clear


def command_clear(io: Io, options: dict) -> int:
    root = io.root
    if own_dir_state(root) == "conflict":
        raise fail("conflict")
    try:
        state = load_state(root)
    except Unreadable:
        state = None
    if state is not None and (state["driver"] is not None or state["launch"] is not None):
        raise fail("running")
    lock = Lock(root)
    if not lock.try_acquire():
        raise fail("running")
    try:
        folder = own_dir(root)
        save_state(root, empty_state([], reset=True))
        cancel = folder / CANCEL_NAME
        if cancel.exists():
            cancel.unlink()
        for entry in folder.iterdir():
            if TEMP_FILE.match(entry.name):
                entry.unlink()
    finally:
        lock.release()
    return io.emit({"cleared": True, "baseline_reset": True})


# -------------------------------------------------------------------- main

HANDLERS = {
    "status": command_status, "brief": command_brief, "run": command_run, "watch": command_watch,
    "cancel": command_cancel, "test": command_test, "finalize": command_finalize, "clear": command_clear,
    "_drive": command_drive,
}


def main(argv: list[str] | None = None, root: Path | None = None, stdout=None, stderr=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    io = Io(Path(root) if root is not None else Path.cwd(),
            stdout if stdout is not None else sys.stdout.buffer,
            stderr if stderr is not None else sys.stderr.buffer)
    try:
        validate_environment()
        command, options = parse_args(argv)
    except Usage:
        return io.emit({"error": USAGE, "reason": "usage"}, EXIT_FAILED)
    if load_grill() is None:
        return io.emit({"error": MESSAGES["dependency"], "reason": "dependency"}, EXIT_STATE)
    try:
        return HANDLERS[command](io, options)
    except Usage:
        return io.emit({"error": USAGE, "reason": "usage"}, EXIT_FAILED)
    except Failure as error:
        if command == "_drive":
            return EXIT_FAILED
        return io.failure(error)
    except OSError as error:
        if command == "_drive":
            return EXIT_FAILED
        return io.emit({"error": MESSAGES["os-error"].format(error.strerror or error), "reason": "os-error"},
                       EXIT_FAILED)


if __name__ == "__main__":
    sys.exit(main())
