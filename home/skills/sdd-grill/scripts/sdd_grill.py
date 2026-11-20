# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Keep the progress of an sdd-grill discussion and check what was generated from it.

Usage:
    uv run sdd_grill.py check     prerequisites, project state, saved progress and what changed
    uv run sdd_grill.py save      validate the full progress read from stdin and save it
    uv run sdd_grill.py verify    check the generated constitution and specs against the summary
    uv run sdd_grill.py focus     point .specify/feature.json at the first spec of this batch
    uv run sdd_grill.py clear     remove the saved progress

Run it from the root of the target project. Output is one JSON object on stdout.
Nothing is loaded or run when this file is imported.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
# 2 is reserved (it means "conflict" for the deploy tool); 4 is not used (no network).
EXIT_NO_SPECKIT = 3

COMMANDS = ("check", "save", "verify", "focus", "clear")
USAGE = "usage: sdd_grill.py check|save|verify|focus|clear"

OWN_DIR = ".specify/sdd-grill"
PROGRESS_NAME = "progress.json"
GITIGNORE_NAME = ".gitignore"
OWN_FILES = (GITIGNORE_NAME, PROGRESS_NAME)
OWN_GITIGNORE = "# Created by sdd-grill. Local discussion progress; never committed.\n*\n"

CONSTITUTION_PATH = ".specify/memory/constitution.md"
SPECS_DIR = "specs"


# ------------------------------------------------------------------ hashing


def normalize_newlines(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def content_hash(data: bytes) -> str:
    """SHA-256 of the content with CRLF and CR turned into LF, so both platforms agree."""
    return hashlib.sha256(normalize_newlines(data)).hexdigest()


def file_hash(path: Path) -> str | None:
    return content_hash(path.read_bytes()) if path.is_file() else None


def spec_folders(root: Path) -> list[str]:
    """Names of the folders directly under specs/ that hold a spec.md, sorted by name."""
    specs = root / SPECS_DIR
    if not specs.is_dir():
        return []
    return sorted(p.name for p in specs.iterdir() if p.is_dir() and (p / "spec.md").is_file())


def git_head(root: Path) -> str | None:
    """The commit HEAD points at; None outside a git repository, without commits, or without git."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    head = done.stdout.strip()
    return head if done.returncode == 0 and head else None


def fingerprint(root: Path) -> dict:
    """What the decisions rest on: the constitution, every spec.md, and git's HEAD."""
    return {
        "constitution": file_hash(root / CONSTITUTION_PATH),
        "specs": {
            f"{SPECS_DIR}/{name}/spec.md": content_hash((root / SPECS_DIR / name / "spec.md").read_bytes())
            for name in spec_folders(root)
        },
        "head": git_head(root),
    }


# ---------------------------------------------------------------- own folder


def own_folder_state(folder: Path) -> str:
    """"absent", "ok", or "conflict" when the folder holds anything sdd-grill did not create."""
    if not folder.exists() and not folder.is_symlink():
        return "absent"
    if not folder.is_dir() or folder.is_symlink():
        return "conflict"
    for entry in folder.iterdir():
        if entry.name not in OWN_FILES or not entry.is_file() or entry.is_symlink():
            return "conflict"
    gitignore = folder / GITIGNORE_NAME
    if gitignore.exists() and normalize_newlines(gitignore.read_bytes()) != OWN_GITIGNORE.encode("utf-8"):
        return "conflict"
    return "ok"


def atomic_write(path: Path, data: bytes) -> None:
    """Write to a temporary file in the same folder, then replace path with it."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ensure_own_folder(folder: Path) -> None:
    """Create the folder and the .gitignore that keeps it (itself included) out of git."""
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / GITIGNORE_NAME).exists():
        atomic_write(folder / GITIGNORE_NAME, OWN_GITIGNORE.encode("utf-8"))


def remove_own_files(folder: Path) -> bool:
    """Remove sdd-grill's two files, and the folder once it is empty. True when a file was removed.

    The caller checks own_folder_state first; nothing else in the folder is touched.
    """
    removed = False
    for name in OWN_FILES:
        path = folder / name
        if path.is_file():
            path.unlink()
            removed = True
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return removed


# ------------------------------------------------------------------- secrets

# Deliberately conservative (research.md R8): a safety net, not a replacement for the skill's instructions.
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])xox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"),
    re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@"),
    re.compile(r"(?i)(?<![A-Za-z])(password|secret|token|api[_-]?key)\s*[=:]\s*\S"),
]


def looks_like_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def find_secret(value, path: str = "") -> str | None:
    """The path of the first string value that looks like a secret, or None. The value itself is never returned."""
    if isinstance(value, str):
        return path if looks_like_secret(value) else None
    if isinstance(value, dict):
        for key, item in value.items():
            found = find_secret(item, f"{path}.{key}" if path else str(key))
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_secret(item, f"{path}[{index}]")
            if found is not None:
                return found
    return None


# ------------------------------------------------------------- project state

SPECKIT_REQUIRED = (
    ".claude/skills/speckit-constitution/SKILL.md",
    ".claude/skills/speckit-specify/SKILL.md",
    ".specify/scripts/bash/resolve-template.sh",
    ".specify/templates/constitution-template.md",
    ".specify/templates/spec-template.md",
)
CONSTITUTION_TEMPLATE_PATH = ".specify/templates/constitution-template.md"
TEMPLATE_MARKERS = (b"[PROJECT_NAME]", b"[PRINCIPLE_1_NAME]")
INIT_OPTIONS_PATH = ".specify/init-options.json"
NUMBERINGS = ("sequential", "timestamp")

NO_SPECKIT = "Spec Kit is not set up in this project; run /sdd-init first."
INCOMPLETE_SPECKIT = (
    "Spec Kit in this project lacks files needed to generate a constitution and specs; it may have changed incompatibly."
)

TIMESTAMP_PREFIX = re.compile(r"^(\d{8}-\d{6})-")
SEQUENTIAL_PREFIX = re.compile(r"^(\d{3,})-")


def speckit_state(root: Path) -> tuple[str, list[str]]:
    if not (root / ".specify").is_dir():
        return "missing", []
    missing = sorted(rel for rel in SPECKIT_REQUIRED if not (root / rel).is_file())
    return ("incomplete", missing) if missing else ("ok", [])


def constitution_state(root: Path) -> str:
    path = root / CONSTITUTION_PATH
    if not path.is_file():
        return "missing"
    content = normalize_newlines(path.read_bytes())
    template = root / CONSTITUTION_TEMPLATE_PATH
    if template.is_file() and normalize_newlines(template.read_bytes()) == content:
        return "template"
    if any(marker in content for marker in TEMPLATE_MARKERS):
        return "template"
    return "written"


def spec_number(name: str) -> str | None:
    """The number a spec folder name starts with: a timestamp, three or more digits, or None."""
    match = TIMESTAMP_PREFIX.match(name) or SEQUENTIAL_PREFIX.match(name)
    return match.group(1) if match else None


def numbering(root: Path) -> str:
    try:
        options = json.loads((root / INIT_OPTIONS_PATH).read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return "sequential"
    if isinstance(options, dict):
        for key in ("feature_numbering", "branch_numbering"):
            if options.get(key) in NUMBERINGS:
                return options[key]
    return "sequential"


def existing_specs(root: Path) -> list[dict]:
    return [{"dir": f"{SPECS_DIR}/{name}", "number": spec_number(name)} for name in spec_folders(root)]


# ------------------------------------------------------------------ progress

SCHEMA = 1
TOOL = "sdd-grill"
PHASES = ("discussing", "confirmed")
STAGES = ("principles", "features", "feature", "summary")
ACTIONS = ("create", "amend", "keep")
STATUSES = ("pending", "discussing", "decided")
FEATURE_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SPEC_DIR = re.compile(r"^specs/([^/\\]+)$")

# Field order of progress.json; the last three are written by the script.
PROGRESS_FIELDS = (
    "schema", "tool", "requirement", "language", "phase", "stage", "current_feature",
    "constitution", "features", "deferred", "for_plan",
)
SCRIPT_FIELDS = ("saved_at", "fingerprint", "baseline")
CONSTITUTION_FIELDS = ("action", "principles", "governance")
PRINCIPLE_FIELDS = ("title", "rules", "rationale")
FEATURE_FIELDS = ("id", "title", "depends_on", "status", "decisions", "spec_dir")
DECISION_FIELDS = ("topic", "decision")
DEFERRED_FIELDS = ("item", "reason", "feature")
FOR_PLAN_FIELDS = ("item", "feature")

NOT_JSON = "progress is not valid JSON: {}"
INVALID = "progress is invalid at {}: {}"
SECRET = "progress at {} looks like a secret; describe what is needed instead of recording the value"
NO_GOING_BACK = "specs were already generated from the confirmed summary; it can no longer go back to discussing"
CONFLICT = ".specify/sdd-grill/ holds files sdd-grill did not create; nothing was written"


class Invalid(Exception):
    def __init__(self, path: str, reason: str):
        super().__init__(INVALID.format(path, reason))
        self.path = path
        self.reason = reason


def _join(path: str, key) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else key


def _object(value, path: str, fields: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict:
    """value must be an object with exactly fields (plus any of optional); returns it in field order."""
    if not isinstance(value, dict):
        raise Invalid(path or "(top level)", "must be an object")
    for key in value:
        if key not in fields and key not in optional:
            raise Invalid(_join(path, key), "is not a known field")
    for key in fields:
        if key not in value:
            raise Invalid(_join(path, key), "is missing")
    return {key: value[key] for key in fields}


def _text(value, path: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise Invalid(path, "must be a string" + (" or null" if nullable else ""))
    if not value.strip():
        raise Invalid(path, "must not be empty")
    return value


def _choice(value, path: str, choices: tuple[str, ...]) -> str:
    if value not in choices or not isinstance(value, str):
        raise Invalid(path, "must be one of " + ", ".join(f'"{c}"' for c in choices))
    return value


def _array(value, path: str) -> list:
    if not isinstance(value, list):
        raise Invalid(path, "must be an array")
    return value


def _texts(value, path: str) -> list[str]:
    return [_text(item, _join(path, i)) for i, item in enumerate(_array(value, path))]


def is_spec_dir_form(value: str) -> bool:
    match = SPEC_DIR.match(value)
    return bool(match) and match.group(1) not in (".", "..")


def validate_progress(data, root: Path) -> dict:
    """Check the rules of data-model.md (1 to 7) and return the progress in field order, without script fields.

    Raises Invalid with the path of the first field that breaks a rule.
    """
    progress = _object(data, "", PROGRESS_FIELDS, SCRIPT_FIELDS)
    schema = progress["schema"]
    if isinstance(schema, bool) or schema != SCHEMA or not isinstance(schema, int):
        raise Invalid("schema", f"must be {SCHEMA}")
    if progress["tool"] != TOOL:
        raise Invalid("tool", f'must be "{TOOL}"')
    _text(progress["requirement"], "requirement")
    _text(progress["language"], "language", nullable=True)
    phase = _choice(progress["phase"], "phase", PHASES)
    stage = _choice(progress["stage"], "stage", STAGES)
    _text(progress["current_feature"], "current_feature", nullable=True)

    constitution = _object(progress["constitution"], "constitution", CONSTITUTION_FIELDS)
    _choice(constitution["action"], "constitution.action", ACTIONS)
    principles = []
    for i, item in enumerate(_array(constitution["principles"], "constitution.principles")):
        path = f"constitution.principles[{i}]"
        principle = _object(item, path, PRINCIPLE_FIELDS)
        _text(principle["title"], path + ".title")
        _texts(principle["rules"], path + ".rules")
        _text(principle["rationale"], path + ".rationale", nullable=True)
        principles.append(principle)
    _texts(constitution["governance"], "constitution.governance")
    constitution["principles"] = principles
    progress["constitution"] = constitution

    features = []
    ids: list[str] = []
    for i, item in enumerate(_array(progress["features"], "features")):
        path = f"features[{i}]"
        entry = _object(item, path, FEATURE_FIELDS)
        fid = _text(entry["id"], path + ".id")
        if not FEATURE_ID.match(fid):
            raise Invalid(path + ".id", "must be lowercase letters and digits joined by single hyphens")
        if fid in ids:
            raise Invalid(path + ".id", f'repeats the id "{fid}"')
        _text(entry["title"], path + ".title")
        later = {f.get("id") for f in progress["features"][i:] if isinstance(f, dict)}
        for j, dep in enumerate(_array(entry["depends_on"], path + ".depends_on")):
            dep_path = f"{path}.depends_on[{j}]"
            _text(dep, dep_path)
            if dep in ids:
                continue
            if dep in later:
                raise Invalid(dep_path, "must name a feature listed before this one")
            if not (is_spec_dir_form(dep) and (root / dep / "spec.md").is_file()):
                raise Invalid(dep_path, "must be the id of an earlier feature or a folder under specs/ that holds a spec.md")
        _choice(entry["status"], path + ".status", STATUSES)
        decisions = []
        for j, decision in enumerate(_array(entry["decisions"], path + ".decisions")):
            decision_path = f"{path}.decisions[{j}]"
            decision = _object(decision, decision_path, DECISION_FIELDS)
            _text(decision["topic"], decision_path + ".topic")
            _text(decision["decision"], decision_path + ".decision")
            decisions.append(decision)
        entry["decisions"] = decisions
        spec_dir = _text(entry["spec_dir"], path + ".spec_dir", nullable=True)
        if spec_dir is not None:
            if phase != "confirmed":
                raise Invalid(path + ".spec_dir", 'must be null until the phase is "confirmed"')
            if not is_spec_dir_form(spec_dir):
                raise Invalid(path + ".spec_dir", "must be a folder directly under specs/, written as specs/<name>")
        ids.append(fid)
        features.append(entry)
    progress["features"] = features

    for name, fields in (("deferred", DEFERRED_FIELDS), ("for_plan", FOR_PLAN_FIELDS)):
        entries = []
        for i, item in enumerate(_array(progress[name], name)):
            path = f"{name}[{i}]"
            entry = _object(item, path, fields)
            for field in fields[:-1]:
                _text(entry[field], f"{path}.{field}")
            owner = _text(entry["feature"], path + ".feature", nullable=True)
            if owner is not None and owner not in ids:
                raise Invalid(path + ".feature", "must be null or the id of a feature")
            entries.append(entry)
        progress[name] = entries

    current = progress["current_feature"]
    if stage == "feature":
        if current not in ids:
            raise Invalid("current_feature", 'must be the id of a feature when the stage is "feature"')
    elif current is not None:
        raise Invalid("current_feature", 'must be null unless the stage is "feature"')

    if phase == "confirmed":
        if stage != "summary":
            raise Invalid("stage", 'must be "summary" when the phase is "confirmed"')
        for i, entry in enumerate(features):
            if entry["status"] != "decided":
                raise Invalid(f"features[{i}].status", 'must be "decided" when the phase is "confirmed"')
        if progress["language"] is None:
            raise Invalid("language", 'must be set when the phase is "confirmed"')
    return progress


def _valid_hashes(value) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def _valid_stored(data: dict) -> bool:
    """The script fields of a stored progress have the shape the script writes."""
    print_ = data.get("fingerprint")
    baseline = data.get("baseline")
    return (
        isinstance(data.get("saved_at"), str)
        and isinstance(print_, dict)
        and set(print_) == {"constitution", "specs", "head"}
        and (print_["constitution"] is None or isinstance(print_["constitution"], str))
        and _valid_hashes(print_["specs"])
        and (print_["head"] is None or isinstance(print_["head"], str))
        and (
            baseline is None
            or (
                isinstance(baseline, dict)
                and set(baseline) == {"constitution", "specs"}
                and (baseline["constitution"] is None or isinstance(baseline["constitution"], str))
                and _valid_hashes(baseline["specs"])
            )
        )
    )


def load_progress(root: Path, folder: str = OWN_DIR) -> tuple[str, dict | None]:
    """("none" | "present" | "unreadable" | "conflict", the stored progress when present)."""
    own = root / folder
    state = own_folder_state(own)
    if state == "conflict":
        return "conflict", None
    path = own / PROGRESS_NAME
    if not path.is_file():
        return "none", None
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
        validate_progress(data, root)
    except (OSError, ValueError, Invalid):
        return "unreadable", None
    if not _valid_stored(data):
        return "unreadable", None
    return "present", data


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ commands


def command_check(io: "Io") -> int:
    root = io.root
    speckit, missing = speckit_state(root)
    progress, saved = "none", None
    changed: list[str] = []
    result = {
        "speckit": speckit,
        "missing": missing,
        "constitution": constitution_state(root),
        "numbering": numbering(root),
        "specs": existing_specs(root),
        "progress": progress,
        "changed": changed,
        "saved": saved,
    }
    if speckit == "missing":
        return io.fail(NO_SPECKIT, EXIT_NO_SPECKIT, **result)
    if speckit == "incomplete":
        return io.fail(INCOMPLETE_SPECKIT, EXIT_NO_SPECKIT, **result)
    return io.emit(result)


def read_stdin_json(io: "Io"):
    raw = io.stdin.read()
    try:
        return json.loads(raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw)
    except UnicodeDecodeError:
        raise ValueError("the input is not UTF-8") from None


def command_save(io: "Io") -> int:
    root = io.root
    try:
        data = read_stdin_json(io)
    except ValueError as error:
        return io.fail(NOT_JSON.format(error))
    try:
        progress = validate_progress(data, root)
    except Invalid as error:
        return io.fail(str(error))

    previous_state, previous = load_progress(root)
    if (
        progress["phase"] == "discussing"
        and previous is not None
        and previous["phase"] == "confirmed"
        and any(f.get("spec_dir") for f in previous["features"])
    ):
        return io.fail(NO_GOING_BACK)
    secret = find_secret(progress)
    if secret is not None:
        return io.fail(SECRET.format(secret))
    own = root / OWN_DIR
    if own_folder_state(own) == "conflict":
        return io.fail(CONFLICT)

    print_ = fingerprint(root)
    recorded = False
    baseline = None
    if progress["phase"] == "confirmed":
        if previous is not None and previous["phase"] == "confirmed" and previous.get("baseline") is not None:
            baseline = previous["baseline"]
        else:
            baseline = {"constitution": print_["constitution"], "specs": print_["specs"]}
            recorded = True
    progress["saved_at"] = utc_now()
    progress["fingerprint"] = print_
    progress["baseline"] = baseline

    ensure_own_folder(own)
    atomic_write(own / PROGRESS_NAME, dumps(progress))
    return io.emit({"saved": f"{OWN_DIR}/{PROGRESS_NAME}", "phase": progress["phase"], "baseline": recorded})


def dumps(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class Io:
    def __init__(self, root: Path, stdin, stdout, stderr):
        self.root = root
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def emit(self, data: dict, code: int = EXIT_OK) -> int:
        self.stdout.write(dumps(data))
        if "error" in data:
            self.stderr.write((data["error"] + "\n").encode("utf-8"))
        return code

    def fail(self, message: str, code: int = EXIT_FAILED, **fields) -> int:
        return self.emit({**fields, "error": message}, code)


def main(argv: list[str] | None = None, root: Path | None = None, stdin=None, stdout=None, stderr=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    io = Io(
        Path(root) if root is not None else Path.cwd(),
        stdin if stdin is not None else sys.stdin.buffer,
        stdout if stdout is not None else sys.stdout.buffer,
        stderr if stderr is not None else sys.stderr.buffer,
    )
    if len(argv) != 1 or argv[0] not in COMMANDS:
        return io.fail(USAGE)
    handler = HANDLERS.get(argv[0])
    if handler is None:
        return io.fail(f"{argv[0]} is not implemented yet")
    try:
        return handler(io)
    except OSError as error:
        return io.fail(f"{argv[0]} failed: {error.strerror or error}")


HANDLERS = {"check": command_check, "save": command_save}


if __name__ == "__main__":
    sys.exit(main())
