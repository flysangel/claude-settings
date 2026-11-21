# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Export an old project's nutrients for sdd-rebuild: check, list, validate and write.

Usage:
    uv run sdd_export.py check    [--project <dir>]                      project state, export folder, generation
    uv run sdd_export.py files    [--project <dir>] [--scope <path>]...  readable files and where secrets are
    uv run sdd_export.py validate [--project <dir>]                      validate the draft read from stdin
    uv run sdd_export.py write    [--project <dir>] --expect <state>     write the confirmed draft read from stdin

Output is one JSON object on stdout. Only `write` writes, and only inside .sdd-export/.
Nothing is loaded or run when this file is imported.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets as random_names
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
# 2 is reserved (it means "conflict" for the deploy tool); 4 is not used (no network).
EXIT_STATE = 3

SCHEMA = 1
TOOL = "sdd-export"
LINEAGE_TOOL = "sdd-rebuild"
LANGUAGE = "zh-Hant"

EXPORT_DIR = ".sdd-export"
NUTRIENTS_NAME = "nutrients.json"
README_NAME = "README.md"
GITATTRIBUTES_NAME = ".gitattributes"
OWN_FILES = (NUTRIENTS_NAME, README_NAME, GITATTRIBUTES_NAME)
GITATTRIBUTES = "# Created by sdd-export; keeps these files LF on every platform.\n* text eol=lf\n"
LINEAGE_PATH = ".sdd-rebuild/lineage.json"
CONSTITUTION_PATH = ".specify/memory/constitution.md"
SPECS_DIR = "specs"

COMMANDS = ("check", "files", "validate", "write")
USAGE = (
    "usage: sdd_export.py check [--project <dir>] | files [--project <dir>] [--scope <path>]... | "
    "validate [--project <dir>] | write [--project <dir>] --expect <state>"
)

NOT_A_FOLDER = "the project folder does not exist or is not a folder"
CONFLICT = ".sdd-export/ holds files sdd-export did not create; nothing was read or written"
CHANGED = ".sdd-export/ changed since it was checked; check again and confirm the differences before writing"
INVALID = "the draft is not valid nutrients"
SECRET = "the draft looks like it contains a secret; describe what is needed instead of recording the value"
COULD_NOT_WRITE = "could not write .sdd-export/: {}"


def utc_today() -> str:
    """Today's date in UTC as YYYY-MM-DD; the only source of exported_at (tests replace it)."""
    return datetime.now(timezone.utc).date().isoformat()


# ----------------------------------------------------------- serialization

# Key order of every object, as data-model.md lists it.
NUTRIENTS_KEYS = (
    "tool", "schema", "generation", "project", "exported_at", "language", "scope",
    "principles", "features", "lessons", "discarded",
)
DRAFT_KEYS = tuple(key for key in NUTRIENTS_KEYS if key not in ("tool", "schema", "exported_at"))
SCRIPT_KEYS = ("tool", "schema", "exported_at")
SCOPE_KEYS = ("coverage", "included")
PRINCIPLE_KEYS = ("id", "origin", "title", "text", "revised", "derived_from", "source", "status", "evidence")
FEATURE_KEYS = (
    "id", "origin", "title", "summary", "revised", "derived_from", "source", "spec", "depends_on", "requirements",
)
REQUIREMENT_KEYS = ("id", "origin", "kind", "text", "revised", "derived_from", "source", "status", "evidence")
LESSON_KEYS = ("id", "origin", "kind", "title", "text", "revised", "derived_from", "status", "evidence")
DISCARDED_KEYS = ("id", "kind", "origin", "discarded_in", "text", "reason")

LINEAGE_KEYS = ("tool", "schema", "generation", "rebuilt_at", "source", "principles", "features", "lessons", "discarded")
LINEAGE_SOURCE_KEYS = ("project", "generation", "nutrients_schema")
LINEAGE_PRINCIPLE_KEYS = ("id", "origin", "title", "text", "revised", "derived_from", "source")
LINEAGE_FEATURE_KEYS = (
    "id", "origin", "title", "summary", "revised", "derived_from", "source", "spec_dir", "spec", "depends_on",
    "requirements",
)
LINEAGE_REQUIREMENT_KEYS = ("id", "origin", "kind", "text", "revised", "derived_from", "source")
LINEAGE_LESSON_KEYS = ("id", "origin", "kind", "title", "text", "revised", "derived_from")

LAYOUTS = {
    "nutrients": {
        None: NUTRIENTS_KEYS, "scope": SCOPE_KEYS, "principles": PRINCIPLE_KEYS, "features": FEATURE_KEYS,
        "requirements": REQUIREMENT_KEYS, "lessons": LESSON_KEYS, "discarded": DISCARDED_KEYS,
    },
    "lineage": {
        None: LINEAGE_KEYS, "source": LINEAGE_SOURCE_KEYS, "principles": LINEAGE_PRINCIPLE_KEYS,
        "features": LINEAGE_FEATURE_KEYS, "requirements": LINEAGE_REQUIREMENT_KEYS,
        "lessons": LINEAGE_LESSON_KEYS, "discarded": DISCARDED_KEYS,
    },
}


def _ordered(value, layout: dict, name):
    """The value with every object's keys in the documented order; unknown keys keep their place at the end."""
    if isinstance(value, list):
        return [_ordered(item, layout, name) for item in value]
    if not isinstance(value, dict):
        return value
    order = layout.get(name, ())
    keys = [key for key in order if key in value] + [key for key in value if key not in order]
    return {key: _ordered(value[key], layout, key) if key in layout else value[key] for key in keys}


def ordered(data: dict, kind: str) -> dict:
    """Nutrients ("nutrients") or a lineage ("lineage") with its keys in the documented order."""
    return _ordered(data, LAYOUTS[kind], None)


def dumps(data) -> bytes:
    """UTF-8 without BOM, LF, two-space indent, non-ASCII kept, one newline at the end."""
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def serialize(data: dict, kind: str = "nutrients") -> bytes:
    """Nutrients or a lineage as bytes, following the shared serialization rules of data-model.md."""
    return dumps(ordered(data, kind))


def normalize_newlines(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def content_hash(data: bytes) -> str:
    """SHA-256 of the content with CRLF and CR turned into LF, so both platforms agree."""
    return hashlib.sha256(normalize_newlines(data)).hexdigest()


class Unreadable(Exception):
    """A file that is not UTF-8 text without a BOM."""


def read_text(path: Path) -> str:
    """The file as text with LF newlines; a BOM or invalid UTF-8 makes it unreadable."""
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise Unreadable("starts with a byte order mark")
    try:
        return normalize_newlines(data).decode("utf-8")
    except UnicodeDecodeError as error:
        raise Unreadable("is not UTF-8") from error


def read_json_object(path: Path) -> dict:
    """A JSON object from path; Unreadable when it is not a UTF-8 JSON object."""
    try:
        value = json.loads(read_text(path))
    except ValueError as error:
        raise Unreadable("is not valid JSON") from error
    if not isinstance(value, dict):
        raise Unreadable("is not a JSON object")
    return value


# -------------------------------------------------------------- paths, ids

DRIVE = re.compile(r"^[A-Za-z]:")
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ID_MAX = 64


def path_problem(path) -> str | None:
    """Why path is not a relative, slash-separated project path, or None when it is one."""
    if not isinstance(path, str) or not path:
        return "is not a non-empty string"
    if "\\" in path:
        return "uses a backslash; separate with /"
    if path.startswith("/") or DRIVE.match(path):
        return "is absolute; use a path relative to the project root"
    if path.startswith("./"):
        return "starts with ./"
    parts = path.split("/")
    if any(part == "" for part in parts):
        return "has an empty segment"
    if any(part in (".", "..") for part in parts):
        return "contains . or .."
    return None


def valid_id(value) -> bool:
    return isinstance(value, str) and len(value) <= ID_MAX and ID_PATTERN.match(value) is not None


def schema_is_newer(value) -> bool:
    """True when value is a schema number this script does not know yet (it must not guess the content)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > SCHEMA


# ------------------------------------------------------------------ secrets

# The same patterns as sdd-grill, copied rather than loaded across skills (this skill runs without sdd-grill), so
# both call the same texts secrets; tests/unit/test_sdd_secret_patterns.py fails when the two copies differ.
# Deliberately conservative: a safety net, not a replacement for the skill's instructions.
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])xox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"),
    # A URL with a user and a password. The scheme is the whole run of scheme characters before "://" and holds a
    # letter; starting only where that run starts scans a long run once, not once per character.
    re.compile(r"(?<![A-Za-z0-9+.-])[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@"),
    re.compile(r"(?i)(?<![A-Za-z])(password|secret|token|api[_-]?key)\s*[=:]\s*\S"),
]


def looks_like_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def secret_lines(text: str) -> list[int]:
    """Line numbers (from 1) of the lines that look like secrets. The values themselves are never returned."""
    return [number for number, line in enumerate(text.split("\n"), start=1) if looks_like_secret(line)]


def scan_file(path: Path) -> list[int]:
    """Line numbers of a readable file that look like secrets; undecodable bytes are replaced, not reported."""
    return secret_lines(normalize_newlines(path.read_bytes()).decode("utf-8", errors="replace"))


SECRET_DIRS = (".ssh", ".aws", ".gnupg")
SECRET_NAMES = (".env", ".netrc", "_netrc", ".npmrc", ".pypirc", "credentials")
SECRET_PREFIXES = (".env.", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials.", "secrets.", "service-account")
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".tfvars", ".tfstate")
SECRET_JSON_YAML = (".json", ".yaml", ".yml")


def is_secret_name(name: str) -> bool:
    name = name.lower()
    if name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES):
        return True
    if name.startswith(SECRET_PREFIXES):
        return not name.startswith("service-account") or name.endswith(".json")
    if ".tfstate." in name:
        return True
    return "secret" in name and name.endswith(SECRET_JSON_YAML)


def is_secret_path(path: str) -> bool:
    """True for a file sdd-export never opens; decided from the path alone, case-insensitively."""
    parts = path.lower().split("/")
    if any(part in SECRET_DIRS for part in parts[:-1]):
        return True
    return is_secret_name(parts[-1])


# ---------------------------------------------------------------------- git


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    """Run a read-only git subcommand in root; None when git cannot be started."""
    try:
        return subprocess.run(["git", "--no-optional-locks", *args], cwd=root, capture_output=True)
    except OSError:
        return None


def is_git_repository(root: Path) -> bool:
    done = run_git(root, "rev-parse", "--is-inside-work-tree")
    return done is not None and done.returncode == 0 and done.stdout.strip() == b"true"


def git_list(root: Path, *args: str) -> list[str] | None:
    """Paths printed by `git ls-files -z <args>`, relative to root; None when git fails."""
    done = run_git(root, "ls-files", "-z", *args)
    if done is None or done.returncode != 0:
        return None
    return [entry.decode("utf-8", errors="surrogateescape") for entry in done.stdout.split(b"\0") if entry]


def commit_exists(root: Path, commit: str) -> bool:
    done = run_git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    return done is not None and done.returncode == 0


# ------------------------------------------------------------- validation

STATUSES = ("confirmed", "pending")
PRINCIPLE_SOURCES = ("constitution", "doc", "code", "maintainer")
FEATURE_SOURCES = ("spec", "code", "mixed", "maintainer")
REQUIREMENT_SOURCES = ("spec", "code", "doc", "maintainer")
REQUIREMENT_KINDS = ("story", "functional", "edge-case", "success-criterion", "assumption")
LESSON_KINDS = ("decision", "pitfall", "reversed")
DISCARDED_KINDS = ("principle", "feature", "requirement", "lesson", "doubt")
COVERAGES = ("full", "partial")
REBUILD = "rebuild"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMMIT = re.compile(r"^commit:([0-9a-f]{7,40})$")
CODE_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})", re.MULTILINE)
MAINTAINER = "maintainer"

# Field rules of each kind of item: "id", "int", "str" (not empty), "ints", "ids", "strs", "str?" (string or
# null), "items" (a list of objects), or a tuple of allowed values.
ITEM_RULES = {
    "principles": {
        "id": "id", "origin": "int", "title": "str", "text": "str", "revised": "ints", "derived_from": "ids",
        "source": PRINCIPLE_SOURCES, "status": STATUSES, "evidence": "strs",
    },
    "features": {
        "id": "id", "origin": "int", "title": "str", "summary": "str", "revised": "ints", "derived_from": "ids",
        "source": FEATURE_SOURCES, "spec": "str?", "depends_on": "ids", "requirements": "items",
    },
    "requirements": {
        "id": "id", "origin": "int", "kind": REQUIREMENT_KINDS, "text": "str", "revised": "ints",
        "derived_from": "ids", "source": REQUIREMENT_SOURCES, "status": STATUSES, "evidence": "strs",
    },
    "lessons": {
        "id": "id", "origin": "int", "kind": LESSON_KINDS, "title": "str", "text": "str", "revised": "ints",
        "derived_from": "ids", "status": STATUSES, "evidence": "strs",
    },
    "discarded": {"id": "id", "kind": DISCARDED_KINDS, "origin": "int", "discarded_in": "int", "text": "str", "reason": "str"},
}
LINEAGE_RULES = {
    "principles": {**{k: v for k, v in ITEM_RULES["principles"].items() if k not in ("status", "evidence")},
                   "source": PRINCIPLE_SOURCES + (REBUILD,)},
    "features": {**{k: v for k, v in ITEM_RULES["features"].items() if k != "source"},
                 "source": FEATURE_SOURCES + (REBUILD,), "spec_dir": "str"},
    "requirements": {**{k: v for k, v in ITEM_RULES["requirements"].items() if k not in ("status", "evidence")},
                     "source": REQUIREMENT_SOURCES + (REBUILD,)},
    "lessons": {k: v for k, v in ITEM_RULES["lessons"].items() if k not in ("status", "evidence")},
    "discarded": ITEM_RULES["discarded"],
}
SECTIONS = ("principles", "features", "lessons", "discarded")
ACTIVE_SECTIONS = ("principles", "features", "requirements", "lessons")
SINGULAR = {"principles": "principle", "features": "feature", "requirements": "requirement", "lessons": "lesson",
            "discarded": "discarded item"}


TOP_LEVEL = "(top level)"
NOT_SHOWN = "(not shown)"
HIDDEN_DETAIL = "this message would repeat text that looks like a secret, so it is not shown"
SECRET_KEY_DETAIL = "a field name here looks like a secret; remove that field"


class Problem:
    """One error: the check that failed, the field path, a sentence that never repeats a secret value."""

    def __init__(self, check: str, path: str, detail: str, secret: bool = False):
        self.check = check
        self.path = path
        self.detail = detail
        self.secret = secret

    def as_dict(self) -> dict:
        # A last safety net: a path or a sentence that would repeat something looking like a secret (an id, a name)
        # is replaced, never printed.
        path = NOT_SHOWN if looks_like_secret(self.path) else self.path
        detail = HIDDEN_DETAIL if looks_like_secret(self.detail) else self.detail
        return {"check": self.check, "path": path, "detail": detail}


def join(path: str, key) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else key


def secret_key(key) -> bool:
    """A field name that looks like a secret: it is reported at the path of the object that holds it."""
    return isinstance(key, str) and looks_like_secret(key)


def holder(path: str) -> str:
    """The path of the object itself, as it is reported when one of its field names looks like a secret."""
    return path or TOP_LEVEL


PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def path_sort_key(path: str) -> tuple:
    """Field paths in reading order: features[2] before features[10]."""
    return tuple((0, "", int(index)) if index else (1, name, 0) for name, index in PATH_TOKEN.findall(path))


def sorted_problems(problems: list[Problem]) -> list[Problem]:
    return sorted(problems, key=lambda problem: path_sort_key(problem.path))


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def shown(value) -> str:
    """A draft value safe to repeat in a message: never a secret, never long."""
    if isinstance(value, str) and (looks_like_secret(value) or "\n" in value or len(value) > 120):
        return "this value"
    return json.dumps(value, ensure_ascii=False)


def rule_problem(value, rule) -> str | None:
    if isinstance(rule, tuple):
        return None if value in rule else "must be one of " + ", ".join(rule)
    if rule == "int":
        return None if is_int(value) else "must be an integer"
    if rule in ("str", "id"):
        if not isinstance(value, str):
            return "must be a string"
        return None if value or rule == "id" else "must not be empty"
    if rule == "str?":
        return None if value is None or (isinstance(value, str) and value) else "must be a path or null"
    if rule == "ints":
        return None if isinstance(value, list) and all(is_int(v) for v in value) else "must be a list of integers"
    if rule == "ids":
        return None if isinstance(value, list) and all(isinstance(v, str) for v in value) else "must be a list of ids"
    if rule == "strs":
        if isinstance(value, list) and all(isinstance(v, str) and v for v in value):
            return None
        return "must be a list of non-empty strings"
    if rule == "items":
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            return "must be a list of objects"
        return None if value else "needs at least one entry"
    raise ValueError(rule)


def check_keys(obj: dict, path: str, required, problems: list[Problem], forbidden=()) -> None:
    for key in required:
        if key not in obj:
            problems.append(Problem("field", join(path, key), f"the key {key} is missing"))
    for key in obj:
        if secret_key(key):
            problems.append(Problem("secret", holder(path), SECRET_KEY_DETAIL, secret=True))
        elif key in forbidden:
            problems.append(Problem("field", join(path, key), f"{key} is filled in by the script; leave it out"))
        elif key not in required:
            problems.append(Problem("field", join(path, key), f"{key} is not a field of the nutrients; remove it"))


def walk_items(data: dict):
    """(section, path, item, feature id or None) for every object item in the four sections and the requirements."""
    for section in SECTIONS:
        entries = data.get(section)
        if not isinstance(entries, list):
            continue
        for index, item in enumerate(entries):
            if not isinstance(item, dict):
                continue
            path = join(section, index)
            yield section, path, item, None
            if section == "features" and isinstance(item.get("requirements"), list):
                for number, entry in enumerate(item["requirements"]):
                    if isinstance(entry, dict):
                        yield "requirements", join(join(path, "requirements"), number), entry, item.get("id")


def check_fields(data: dict, rules: dict, problems: list[Problem]) -> None:
    for section in SECTIONS:
        entries = data.get(section)
        if section in data and not isinstance(entries, list):
            problems.append(Problem("field", section, "must be a list"))
        elif isinstance(entries, list):
            for index, item in enumerate(entries):
                if not isinstance(item, dict):
                    problems.append(Problem("field", join(section, index), "must be an object"))
    for section, path, item, _ in walk_items(data):
        table = rules[section]
        check_keys(item, path, tuple(table), problems)
        for key, rule in table.items():
            if key not in item:
                continue
            if rule == "strs" and isinstance(item[key], list):
                for index, value in enumerate(item[key]):
                    if not isinstance(value, str) or not value:
                        problems.append(Problem("field", join(join(path, key), index), "must be a non-empty string"))
                continue
            problem = rule_problem(item[key], rule)
            if problem:
                problems.append(Problem("field", join(path, key), problem))


def strings_of(value, path: str = ""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            # Never build a path from a field name that looks like a secret; check_keys reports that name.
            yield from strings_of(item, holder(path) if secret_key(key) else join(path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings_of(item, join(path, index))


def check_ids(data: dict, problems: list[Problem], unique_with_discarded: bool) -> None:
    seen: dict[str, str] = {}
    seen_discarded: dict[str, str] = {}
    for section, path, item, _ in walk_items(data):
        value = item.get("id")
        if not isinstance(value, str):
            continue
        if not valid_id(value):
            problems.append(Problem("id", join(path, "id"), "an id is lowercase letters and digits joined by single "
                                    "hyphens, at most 64 characters"))
            continue
        table = seen_discarded if section == "discarded" and not unique_with_discarded else seen
        if value in table:
            problems.append(Problem("id", join(path, "id"), f"the id {value} is already used at {table[value]}"))
        else:
            table[value] = path
        for key in ("derived_from", "depends_on"):
            entries = item.get(key)
            if isinstance(entries, list):
                for index, entry in enumerate(entries):
                    if isinstance(entry, str) and not valid_id(entry):
                        problems.append(Problem("id", join(join(path, key), index), "is not a valid id"))


def check_ranges(data: dict, generation, problems: list[Problem]) -> None:
    if not is_int(generation) or generation < 1:
        return
    for section, path, item, _ in walk_items(data):
        origin = item.get("origin")
        if not is_int(origin):
            continue
        if not 1 <= origin <= generation:
            problems.append(Problem("range", join(path, "origin"), f"origin must be between 1 and the generation {generation}"))
            continue
        if section == "discarded":
            when = item.get("discarded_in")
            if is_int(when) and not origin <= when <= generation:
                problems.append(Problem("range", join(path, "discarded_in"),
                                        f"discarded_in must be between the origin {origin} and the generation {generation}"))
            continue
        revised = item.get("revised")
        if isinstance(revised, list) and all(is_int(v) for v in revised):
            increasing = all(a < b for a, b in zip(revised, revised[1:]))
            if not increasing or any(not origin < v <= generation for v in revised):
                problems.append(Problem("range", join(path, "revised"), "revised must be strictly increasing, after the "
                                        f"origin {origin} and not after the generation {generation}"))


def check_code_blocks(data: dict, problems: list[Problem]) -> None:
    for path, value in strings_of(data):
        if CODE_FENCE.search(value):
            problems.append(Problem("code-block", path, "code blocks do not belong in the nutrients; describe the "
                                    "behaviour instead"))


def check_secrets(data: dict, problems: list[Problem]) -> None:
    for path, value in strings_of(data):
        if looks_like_secret(value):
            problems.append(Problem("secret", path, "this text looks like a secret; describe what is needed instead "
                                    "of recording the value", secret=True))


def check_dependencies(data: dict, problems: list[Problem]) -> None:
    features = data.get("features")
    if not isinstance(features, list):
        return
    before: set[str] = set()
    for index, item in enumerate(features):
        if not isinstance(item, dict):
            continue
        entries = item.get("depends_on")
        if isinstance(entries, list):
            for number, entry in enumerate(entries):
                if isinstance(entry, str) and valid_id(entry) and entry not in before:
                    problems.append(Problem("dependency", join(join(join("features", index), "depends_on"), number),
                                            f"{entry} is not a feature listed before this one"))
        if isinstance(item.get("id"), str):
            before.add(item["id"])


def check_unsupported(data: dict, problems: list[Problem]) -> None:
    for section, path, item, _ in walk_items(data):
        if section in ("principles", "requirements", "lessons") and item.get("status") == "confirmed" \
                and item.get("evidence") == []:
            problems.append(Problem("unsupported", path, "a confirmed item needs at least one piece of evidence; mark "
                                    "it pending or add evidence"))


def check_top(data: dict, problems: list[Problem], draft: bool) -> None:
    if draft:
        check_keys(data, "", DRAFT_KEYS, problems, forbidden=SCRIPT_KEYS)
    else:
        check_keys(data, "", NUTRIENTS_KEYS, problems)
        if "schema" in data and not is_int(data["schema"]):
            problems.append(Problem("field", "schema", "must be an integer"))
        if "exported_at" in data and not (isinstance(data["exported_at"], str) and DATE.match(data["exported_at"])):
            problems.append(Problem("field", "exported_at", "must be a date written YYYY-MM-DD"))
    if "generation" in data and not (is_int(data["generation"]) and data["generation"] >= 1):
        problems.append(Problem("field", "generation", "must be an integer of at least 1"))
    if "project" in data:
        name = data["project"]
        if not isinstance(name, str) or not name:
            problems.append(Problem("field", "project", "must be a non-empty string"))
        elif "/" in name or "\\" in name:
            problems.append(Problem("field", "project", "must be a name, not a path"))
    if "language" in data and data["language"] != LANGUAGE:
        problems.append(Problem("field", "language", f"must be {LANGUAGE}"))
    if "scope" in data:
        scope = data["scope"]
        if not isinstance(scope, dict):
            problems.append(Problem("field", "scope", "must be an object"))
        else:
            check_keys(scope, "scope", SCOPE_KEYS, problems)
            if "coverage" in scope and scope["coverage"] not in COVERAGES:
                problems.append(Problem("field", "scope.coverage", "must be one of full, partial"))
            if "included" in scope and rule_problem(scope["included"], "strs"):
                problems.append(Problem("field", "scope.included", "must be a list of paths"))
    if isinstance(data.get("features"), list) and not data["features"]:
        problems.append(Problem("field", "features", "needs at least one feature"))


def evidence_problem(root: Path | None, value: str, git: dict) -> tuple[str, bool] | None:
    """Why one piece of evidence is not acceptable (and whether it is a secret file), or None."""
    if value == MAINTAINER:
        return None
    if value.startswith("commit:"):
        match = COMMIT.match(value)
        if not match:
            return "a commit is written commit:<7 to 40 lowercase hexadecimal characters>", False
        if root is None:
            return None
        if git.get("repo") is None:
            git["repo"] = is_git_repository(root)
        if not git["repo"]:
            return "the project is not a git repository, so a commit cannot be evidence", False
        return None if commit_exists(root, match.group(1)) else ("this commit does not exist in the repository", False)
    problem = path_problem(value)
    if problem:
        return f"the path {problem}", False
    if is_secret_path(value):
        return "this path is a secret file, which sdd-export never opens", True
    if root is None:
        return None
    target = root / value
    if not target.exists():
        return "this path does not exist in the project", False
    if not inside(root, os.path.realpath(target)):
        return "this path leads outside the project", False
    excluded = excluded_category(value, target.is_dir())
    if excluded is None and target.is_file() and value != LINEAGE_PATH:
        excluded = file_category(root, value)[0]
        if excluded is None:
            if git.get("repo") is None:
                git["repo"] = is_git_repository(root)
            if git["repo"] and value != CONSTITUTION_PATH and not git_list(root, "--cached", "--others", "--exclude-standard", "--", value):
                excluded = "ignored"
    if excluded and value != LINEAGE_PATH:
        return f"this path is excluded from reading ({excluded})", False
    return None


def check_evidence(data: dict, root: Path | None, problems: list[Problem]) -> None:
    git: dict = {}
    for section, path, item, _ in walk_items(data):
        entries = item.get("evidence")
        if section == "discarded" or not isinstance(entries, list):
            continue
        for index, value in enumerate(entries):
            if isinstance(value, str) and value:
                found = evidence_problem(root, value, git)
                if found:
                    problems.append(Problem("evidence", join(join(path, "evidence"), index), found[0], secret=found[1]))


def check_specs(data: dict, root: Path | None, problems: list[Problem]) -> None:
    features = data.get("features")
    if not isinstance(features, list):
        return
    for index, item in enumerate(features):
        if not isinstance(item, dict):
            continue
        path = join(join("features", index), "spec")
        spec = item.get("spec")
        if item.get("source") in ("spec", "mixed") and spec is None and "spec" in item:
            problems.append(Problem("spec", path, "a feature taken from a spec names that spec"))
        elif isinstance(spec, str) and spec:
            problem = path_problem(spec)
            if problem:
                problems.append(Problem("spec", path, f"the path {problem}"))
            elif root is not None and not (root / spec).is_file():
                problems.append(Problem("spec", path, "this spec file does not exist in the project"))


def check_scope(data: dict, root: Path | None, problems: list[Problem]) -> None:
    scope = data.get("scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("included"), list):
        return
    included = scope["included"]
    if scope.get("coverage") == "full" and included:
        problems.append(Problem("scope", "scope.included", "a full export includes everything; leave included empty"))
    if scope.get("coverage") == "partial":
        if not included:
            problems.append(Problem("scope", "scope.included", "a partial export lists the paths it covers"))
        for index, value in enumerate(included):
            if not isinstance(value, str):
                continue
            problem = path_problem(value)
            if problem:
                problems.append(Problem("scope", join("scope.included", index), f"the path {problem}"))
            elif root is not None and not (root / value).exists():
                problems.append(Problem("scope", join("scope.included", index), "this path does not exist in the project"))


def structure_problems(data: dict, draft: bool) -> list[Problem]:
    """Problems found from the content alone (no files are looked at)."""
    problems: list[Problem] = []
    check_top(data, problems, draft)
    check_fields(data, ITEM_RULES, problems)
    check_ids(data, problems, unique_with_discarded=False)
    check_ranges(data, data.get("generation"), problems)
    check_code_blocks(data, problems)
    check_unsupported(data, problems)
    check_dependencies(data, problems)
    return problems


def validate_draft(draft, lineage: dict | None, existing: dict | None, root: Path | None) -> list[Problem]:
    """Every problem of a draft, sorted by field path; root None skips the checks that look at files."""
    if not isinstance(draft, dict):
        return [Problem("json", "", "the draft must be a JSON object")]
    problems = structure_problems(draft, draft=True)
    check_secrets(draft, problems)
    check_evidence(draft, root, problems)
    check_specs(draft, root, problems)
    check_scope(draft, root, problems)
    problems += generation_problems(draft, lineage, existing)
    return sorted_problems(problems)


TEXT_FIELDS = ("title", "text", "summary")


def active_items(data: dict | None) -> dict[str, tuple[str, str, dict]]:
    """id -> (section, path, item) for the principles, features, requirements and lessons of data."""
    result: dict[str, tuple[str, str, dict]] = {}
    for section, path, item, _ in walk_items(data or {}):
        if section != "discarded" and isinstance(item.get("id"), str):
            result.setdefault(item["id"], (section, path, item))
    return result


def discarded_items(data: dict | None) -> list[tuple[str, dict]]:
    return [(path, item) for section, path, item, _ in walk_items(data or {})
            if section == "discarded" and isinstance(item.get("id"), str)]


def derived_sources(data: dict | None) -> dict[str, set[str]]:
    """id -> the derived_from that data records for that item."""
    result: dict[str, set[str]] = {}
    for _, (_, _, item) in active_items(data).items():
        if isinstance(item.get("derived_from"), list):
            result[item["id"]] = {entry for entry in item["derived_from"] if isinstance(entry, str)}
    return result


def created_here(found: dict[str, tuple[str, str, dict]], item_id: str, section: str, generation: int) -> bool:
    """Whether found holds an active item with this id, of the same kind, created in this generation."""
    same = found.get(item_id)
    return same is not None and same[2].get("origin") == generation and same[0] == section


def generation_problems(draft: dict, lineage: dict | None, existing: dict | None) -> list[Problem]:
    """The generation rules 1 to 9 of data-model.md, checked against the lineage L and the existing nutrients N."""
    problems: list[Problem] = []
    generation = draft_generation(lineage)
    if is_int(draft.get("generation")) and draft["generation"] != generation:
        problems.append(Problem("generation", "generation", f"this project is generation {generation}; use the "
                                "generation that check reports"))
    items = active_items(draft)
    gone = {item["id"]: (path, item) for path, item in discarded_items(draft)}
    derived = {entry for _, _, item in items.values() if isinstance(item.get("derived_from"), list)
               for entry in item["derived_from"] if isinstance(entry, str)}
    in_lineage = active_items(lineage)
    in_existing = active_items(existing)
    lineage_ids = set(in_lineage) | {item["id"] for _, item in discarded_items(lineage)}
    known_ids = lineage_ids | set(in_existing) | {item["id"] for _, item in discarded_items(existing)}
    lineage_derived, existing_derived = derived_sources(lineage), derived_sources(existing)
    # ids that once existed and were merged or split away: they live on only in derived_from, and stay taken.
    historic_ids = {entry for sources in (*lineage_derived.values(), *existing_derived.values()) for entry in sources}

    # Rule 2: nothing of the lineage disappears silently.
    for item_id, (section, _, _) in in_lineage.items():
        if item_id not in items and item_id not in gone and item_id not in derived:
            top = "features" if section == "requirements" else section
            problems.append(Problem("lineage-item-missing", top, f"{SINGULAR[section]} '{item_id}' from the lineage is "
                                    "neither kept, derived from, nor discarded"))
    for item_id, (section, path, item) in items.items():
        origin = item.get("origin")
        if not is_int(origin):
            continue
        prior = in_lineage.get(item_id)
        if prior is None and item_id in in_existing and is_int(in_existing[item_id][2].get("origin")) \
                and in_existing[item_id][2]["origin"] < generation:
            prior = in_existing[item_id]
        # Rule 3: an inherited item keeps its origin.
        if prior is not None and is_int(prior[2].get("origin")) and prior[2]["origin"] != origin:
            problems.append(Problem("origin-changed", join(path, "origin"), f"'{item_id}' first appeared in generation "
                                    f"{prior[2]['origin']}; keep that origin"))
        # Rule 4: an item from an earlier generation can be found there.
        if origin < generation and item_id not in in_lineage and item_id not in in_existing:
            problems.append(Problem("origin-unknown", join(path, "origin"), f"'{item_id}' says it comes from generation "
                                    f"{origin}, but neither the lineage nor the existing nutrients hold it"))
        # Rule 5: a changed inherited text marks this generation in revised. Items created in this generation
        # (origin equal to it) are not checked: their text is this generation's version.
        if item_id in in_lineage and origin < generation:
            before = in_lineage[item_id][2]
            changed = any(key in item and key in before and item[key] != before[key] for key in TEXT_FIELDS)
            revised = item.get("revised") if isinstance(item.get("revised"), list) else []
            if changed and generation not in revised:
                problems.append(Problem("revision-unmarked", join(path, "revised"), f"'{item_id}' differs from the "
                                        f"lineage; add {generation} to revised"))
        # Rule 8: derived_from points at known items, or repeats what an earlier generation recorded.
        sources = item.get("derived_from") if isinstance(item.get("derived_from"), list) else []
        recorded = lineage_derived.get(item_id, set()) | existing_derived.get(item_id, set())
        for index, entry in enumerate(sources):
            if isinstance(entry, str) and entry not in known_ids and entry not in recorded:
                problems.append(Problem("derived-unknown", join(join(path, "derived_from"), index), f"'{entry}' is not "
                                        "an item of the lineage or the existing nutrients"))
        # Rule 9: an item new in this generation does not take an id the lineage already used, nor one that any
        # derived_from of the lineage or the existing nutrients names, unless it is that very item: one the rebuild
        # created in this generation, or (for the derived_from ids only) one an earlier export of this generation
        # wrote and still holds.
        if origin == generation and (item_id in lineage_ids or item_id in historic_ids):
            if not created_here(in_lineage, item_id, section, generation) \
                    and (item_id in lineage_ids or not created_here(in_existing, item_id, section, generation)):
                problems.append(Problem("id-reused", join(path, "id"), f"the id '{item_id}' was already used by the "
                                        "lineage or the existing nutrients; choose a new id"))
    # Rule 6: earlier discards stay as they are.
    required: dict[str, dict] = {}
    for _, item in discarded_items(lineage):
        required.setdefault(item["id"], item)
    for _, item in discarded_items(existing):
        if is_int(item.get("discarded_in")) and item["discarded_in"] < generation:
            required.setdefault(item["id"], item)
    for item_id, item in required.items():
        if item_id not in gone or gone[item_id][1] != item:
            problems.append(Problem("discard-lost", "discarded", f"the discarded item '{item_id}' of an earlier "
                                    "generation must stay in discarded unchanged"))
    # Rule 7: a discarded id is not an active item.
    for item_id, (path, _) in gone.items():
        if item_id in items:
            problems.append(Problem("discarded-active", join(path, "id"), f"'{item_id}' is both discarded and kept"))
    return problems


def has_field_problems(problems: list[Problem]) -> bool:
    return any(problem.check in ("json", "field") for problem in problems)


def draft_generation(lineage: dict | None) -> int:
    return lineage["generation"] if lineage else 1


def counts_of(data: dict, generation) -> dict | None:
    if not isinstance(data, dict):
        return None
    counts = {"principles": 0, "features": 0, "requirements": 0, "lessons": 0, "discarded": 0,
              "pending": 0, "inherited": 0, "new": 0}
    for section, _, item, _ in walk_items(data):
        counts[section] += 1
        if section == "discarded":
            continue
        if item.get("status") == "pending":
            counts["pending"] += 1
        if is_int(item.get("origin")) and is_int(generation):
            if item["origin"] < generation:
                counts["inherited"] += 1
            elif item["origin"] == generation:
                counts["new"] += 1
    return counts


# ------------------------------------------------------------------- diff


def item_title(item: dict) -> str:
    if isinstance(item.get("title"), str):
        return item["title"]
    text = item.get("text") if isinstance(item.get("text"), str) else ""
    return text.split("\n", 1)[0][:80]


def indexed(data: dict) -> dict[str, dict[str, tuple]]:
    """section -> id -> (item without nested requirements, owning feature id)."""
    result: dict[str, dict[str, tuple]] = {section: {} for section in ACTIVE_SECTIONS + ("discarded",)}
    for section, _, item, owner in walk_items(data):
        if isinstance(item.get("id"), str):
            plain = {key: value for key, value in item.items() if key != "requirements"}
            result[section].setdefault(item["id"], (plain, owner))
    return result


def compute_diff(old: dict | None, new: dict) -> dict:
    """What changes from the existing nutrients (None: there are none) to the draft, by id and section."""
    new = ordered(new, "nutrients")
    diff = {"base": "none", "generation": None, "scope": None, "added": [], "removed": [], "changed": [],
            "order_changed": False}
    after = indexed(new)
    if old is None:
        for section in ("principles", "features", "requirements", "lessons", "discarded"):
            for item_id, (item, _) in after[section].items():
                diff["added"].append({"section": section, "id": item_id, "title": item_title(item)})
        return order_entries(diff, new)
    old = ordered(old, "nutrients")
    diff["base"] = "nutrients"
    if old.get("generation") != new.get("generation"):
        diff["generation"] = {"from": old.get("generation"), "to": new.get("generation")}
    if old.get("scope") != new.get("scope"):
        diff["scope"] = {"from": old.get("scope"), "to": new.get("scope")}
    before = indexed(old)
    for section in ("principles", "features", "requirements", "lessons", "discarded"):
        for item_id, (item, owner) in after[section].items():
            if item_id not in before[section]:
                diff["added"].append({"section": section, "id": item_id, "title": item_title(item)})
                continue
            previous, previous_owner = before[section][item_id]
            fields = []
            if section == "requirements" and owner != previous_owner:
                fields.append({"field": "feature", "from": previous_owner, "to": owner})
            for key in list(previous) + [k for k in item if k not in previous]:
                if key != "id" and previous.get(key) != item.get(key):
                    fields.append({"field": key, "from": previous.get(key), "to": item.get(key)})
            if fields:
                diff["changed"].append({"section": section, "id": item_id, "fields": fields})
        for item_id, (item, _) in before[section].items():
            if item_id not in after[section]:
                diff["removed"].append({"section": section, "id": item_id, "title": item_title(item)})
    old_order = [i for i in feature_ids(old) if i in after["features"]]
    new_order = [i for i in feature_ids(new) if i in before["features"]]
    diff["order_changed"] = old_order != new_order
    return order_entries(diff, new)


def feature_ids(data: dict) -> list[str]:
    return [item["id"] for section, _, item, _ in walk_items(data) if section == "features" and isinstance(item.get("id"), str)]


def order_entries(diff: dict, new: dict) -> dict:
    rank = {"principles": 0, "features": 1, "requirements": 2, "lessons": 3, "discarded": 4}
    for key in ("added", "removed", "changed"):
        diff[key].sort(key=lambda entry: rank[entry["section"]])
    return diff


# ----------------------------------------------------------------- README

MARKER = "<!-- Generated by sdd-export from nutrients.json; do not edit. source-sha256: {} view-sha256: {} -->"
MARKER_PATTERN = re.compile(
    r"^<!-- Generated by sdd-export from nutrients\.json; do not edit\. "
    r"source-sha256: ([0-9a-f]{64}) view-sha256: ([0-9a-f]{64}) -->$"
)
KIND_HEADINGS = (
    ("story", "User stories"), ("functional", "Functional requirements"), ("edge-case", "Edge cases"),
    ("success-criterion", "Success criteria"), ("assumption", "Assumptions"),
)
LESSON_HEADINGS = (("decision", "Decisions"), ("pitfall", "Pitfalls"), ("reversed", "Reversed approaches"))


def code_list(values) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def revised_text(item: dict) -> str:
    return ", ".join(str(v) for v in item.get("revised", [])) or "none"


def indented(text: str, prefix: str = "  ") -> list[str]:
    return [prefix + line if line else "" for line in text.split("\n")]


def cell(text) -> str:
    return " ".join(str(text).split("\n")).replace("|", "\\|")


def render_body(data: dict) -> str:
    """README.md without its first line, decided by the nutrients alone."""
    lines: list[str] = []
    add = lines.append
    scope = data["scope"]
    counts = counts_of(data, data["generation"])
    add(f"# Nutrients: {data['project']}")
    add("")
    add(f"- Generation: {data['generation']}")
    add(f"- Exported: {data['exported_at']}")
    add("- Scope: " + ("full" if scope["coverage"] == "full" else "partial (" + code_list(scope["included"]) + ")"))
    add(f"- Contents: {counts['principles']} principles, {counts['features']} features, {counts['requirements']} "
        f"requirements, {counts['lessons']} lessons, {counts['discarded']} discarded; {counts['pending']} pending; "
        f"{counts['inherited']} inherited, {counts['new']} new")
    add("")
    add("Source of truth: `nutrients.json` in this folder. This file is regenerated from it.")
    add("")
    add("## Principles")
    add("")
    if not data["principles"]:
        add("None.")
        add("")
    for item in data["principles"]:
        add(f"### {item['title']} (`{item['id']}`)" + (" (pending)" if item["status"] == "pending" else ""))
        add("")
        add(f"- Origin: generation {item['origin']}; revised in: {revised_text(item)}")
        add(f"- Source: {item['source']}; status: {item['status']}")
        add(f"- Evidence: {code_list(item['evidence'])}")
        if item["derived_from"]:
            add(f"- Derived from: {code_list(item['derived_from'])}")
        add("")
        lines.extend(item["text"].split("\n"))
        add("")
    add("## Features")
    add("")
    for item in data["features"]:
        add(f"### {item['title']} (`{item['id']}`)")
        add("")
        lines.extend(item["summary"].split("\n"))
        add("")
        add(f"- Origin: generation {item['origin']}; revised in: {revised_text(item)}")
        add(f"- Source: {item['source']}" + (f" (`{item['spec']}`)" if item["spec"] else ""))
        add(f"- Depends on: {code_list(item['depends_on'])}")
        if item["derived_from"]:
            add(f"- Derived from: {code_list(item['derived_from'])}")
        add("")
        for kind, heading in KIND_HEADINGS:
            entries = [entry for entry in item["requirements"] if entry["kind"] == kind]
            if not entries:
                continue
            add(f"#### {heading}")
            add("")
            for entry in entries:
                pending = " (pending)" if entry["status"] == "pending" else ""
                derived = f"; derived from: {code_list(entry['derived_from'])}" if entry["derived_from"] else ""
                add(f"- `{entry['id']}`{pending}: origin {entry['origin']}; revised in: {revised_text(entry)}; "
                    f"source: {entry['source']}; status: {entry['status']}; evidence: {code_list(entry['evidence'])}"
                    f"{derived}")
                add("")
                lines.extend(indented(entry["text"]))
                add("")
    add("## Lessons")
    add("")
    if not data["lessons"]:
        add("None.")
        add("")
    for kind, heading in LESSON_HEADINGS:
        entries = [entry for entry in data["lessons"] if entry["kind"] == kind]
        if not entries:
            continue
        add(f"### {heading}")
        add("")
        for entry in entries:
            pending = " (pending)" if entry["status"] == "pending" else ""
            add(f"#### {entry['title']} (`{entry['id']}`){pending}")
            add("")
            add(f"- Origin: generation {entry['origin']}; revised in: {revised_text(entry)}; status: {entry['status']}")
            add(f"- Evidence: {code_list(entry['evidence'])}")
            if entry["derived_from"]:
                add(f"- Derived from: {code_list(entry['derived_from'])}")
            add("")
            lines.extend(entry["text"].split("\n"))
            add("")
    add("## Discarded")
    add("")
    if not data["discarded"]:
        add("None.")
    else:
        add("| ID | Kind | Origin | Discarded in | Content | Reason |")
        add("|---|---|---|---|---|---|")
        for entry in data["discarded"]:
            add(f"| `{entry['id']}` | {entry['kind']} | {entry['origin']} | {entry['discarded_in']} | "
                f"{cell(entry['text'])} | {cell(entry['reason'])} |")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_readme(nutrients: dict) -> bytes:
    """README.md for the nutrients: the marker line with both hashes, then the readable body."""
    data = ordered(nutrients, "nutrients")
    body = render_body(data).encode("utf-8")
    source = content_hash(serialize(data, "nutrients"))
    marker = MARKER.format(source, content_hash(body))
    return marker.encode("utf-8") + b"\n" + body


# -------------------------------------------------------- export folder


def load_nutrients(path: Path) -> tuple[str, dict | None, list[Problem]]:
    """The state of a nutrients.json (none, conflict, unreadable, newer, invalid, ours), its content, its problems."""
    if not path.exists():
        return "none", None, []
    try:
        data = read_json_object(path)
    except (Unreadable, OSError) as error:
        return "unreadable", None, [Problem("json", "", f"nutrients.json {error}")]
    if data.get("tool") != TOOL:
        return "conflict", None, []
    if schema_is_newer(data.get("schema")):
        return "newer", None, []
    problems = structure_problems(data, draft=False)
    if is_int(data.get("schema")) and data["schema"] != SCHEMA:
        problems.append(Problem("field", "schema", f"must be {SCHEMA}"))
    # Hand edits after the export may have added a secret: such nutrients are invalid, and only the field paths
    # are reported, so that the value never reaches the output.
    check_secrets(data, problems)
    check_evidence(data, None, problems)
    check_specs(data, None, problems)
    check_scope(data, None, problems)
    if problems:
        return "invalid", None, sorted_problems(problems)
    return "ours", data, []


def export_folder(root: Path) -> dict:
    """The state of .sdd-export/: export_dir, conflicts, nutrients, view, gitattributes, state, existing, errors."""
    folder = root / EXPORT_DIR
    result = {"export_dir": "none", "conflicts": [], "nutrients": "none", "view": "none", "view_secret_lines": [],
              "gitattributes": "missing", "state": "none", "existing": None, "errors": []}
    if not folder.exists() and not folder.is_symlink():
        return result
    if folder.is_symlink() or not folder.is_dir():
        return {**result, "export_dir": "conflict", "conflicts": [EXPORT_DIR], "nutrients": None, "view": None,
                "view_secret_lines": None, "gitattributes": None, "state": None}
    entries = sorted(folder.iterdir(), key=lambda p: p.name)
    strangers = [f"{EXPORT_DIR}/{entry.name}" for entry in entries
                 if entry.name not in OWN_FILES or entry.is_symlink() or not entry.is_file()]
    if not entries:
        return {**result, "export_dir": "empty"}
    nutrients_path = folder / NUTRIENTS_NAME
    if not strangers and not nutrients_path.exists():
        strangers = [f"{EXPORT_DIR}/{entry.name}" for entry in entries]
    if strangers:
        return {**result, "export_dir": "conflict", "conflicts": strangers, "nutrients": None, "view": None,
                "view_secret_lines": None, "gitattributes": None, "state": None}
    status, data, problems = load_nutrients(nutrients_path)
    if status == "conflict":
        return {**result, "export_dir": "conflict", "conflicts": [f"{EXPORT_DIR}/{NUTRIENTS_NAME}"], "nutrients": None,
                "view": None, "view_secret_lines": None, "gitattributes": None, "state": None}
    result.update(export_dir=status, existing=data, errors=problems)
    result.update(edit_state(folder))
    return result


def edit_state(folder: Path) -> dict:
    """nutrients, view, view_secret_lines, gitattributes and state, from the files and the README marker."""
    nutrients_path, readme_path = folder / NUTRIENTS_NAME, folder / README_NAME
    nutrients_hash = content_hash(nutrients_path.read_bytes()) if nutrients_path.is_file() else None
    readme = normalize_newlines(readme_path.read_bytes()) if readme_path.is_file() else None
    marker = None
    if readme is not None:
        first, _, rest = readme.partition(b"\n")
        match = MARKER_PATTERN.match(first.decode("utf-8", errors="replace"))
        marker = (match.group(1), match.group(2), content_hash(rest)) if match else None
    if nutrients_hash is None:
        nutrients = "none"
    elif marker is None:
        nutrients = "unknown"
    else:
        nutrients = "unchanged" if marker[0] == nutrients_hash else "edited"
    if nutrients_hash is None and readme is None:
        view = "none"
    elif readme is None:
        view = "missing"
    elif marker is None or marker[2] != marker[1]:
        view = "edited"
    else:
        view = "current" if marker[0] == nutrients_hash else "stale"
    # The README's lines that look like secrets (numbers only), found as `files` finds secret_hits: a hand edit may
    # have put one there, and stage 7 must then not read the file. Undecodable bytes are replaced, not reported.
    secret_lines_of_view = secret_lines(readme.decode("utf-8", errors="replace")) if readme is not None else []
    attributes = folder / GITATTRIBUTES_NAME
    if not attributes.is_file():
        gitattributes = "missing"
    else:
        gitattributes = "ok" if normalize_newlines(attributes.read_bytes()) == GITATTRIBUTES.encode("utf-8") else "edited"
    if nutrients_hash is None and readme is None:
        state = "none"
    else:
        readme_hash = content_hash(readme) if readme is not None else ""
        state = hashlib.sha256(f"{nutrients_hash or ''}\n{readme_hash}".encode("ascii")).hexdigest()
    return {"nutrients": nutrients, "view": view, "view_secret_lines": secret_lines_of_view, "gitattributes": gitattributes,
            "state": state}


# ---------------------------------------------------------------- lineage


SPEC_DIR_PATTERN = re.compile(r"^specs/[^/]+$")


def lineage_problems(data: dict) -> list[Problem]:
    """What data-model.md lets sdd-export check in a lineage written by sdd-rebuild."""
    problems: list[Problem] = []
    check_keys(data, "", LINEAGE_KEYS, problems)
    if "schema" in data and data["schema"] != SCHEMA:
        problems.append(Problem("field", "schema", f"must be {SCHEMA}"))
    if "rebuilt_at" in data and not (isinstance(data["rebuilt_at"], str) and DATE.match(data["rebuilt_at"])):
        problems.append(Problem("field", "rebuilt_at", "must be a date written YYYY-MM-DD"))
    generation = data.get("generation")
    if "generation" in data and not (is_int(generation) and generation >= 2):
        problems.append(Problem("generation", "generation", "the generation of a rebuilt project is at least 2"))
        generation = None
    source = data.get("source")
    if "source" in data:
        if not isinstance(source, dict):
            problems.append(Problem("field", "source", "must be an object"))
        else:
            check_keys(source, "source", LINEAGE_SOURCE_KEYS, problems)
            if "project" in source and rule_problem(source["project"], "str"):
                problems.append(Problem("field", "source.project", "must be a non-empty string"))
            for key in ("generation", "nutrients_schema"):
                if key in source and not (is_int(source[key]) and source[key] >= 1):
                    problems.append(Problem("field", f"source.{key}", "must be an integer of at least 1"))
            if is_int(generation) and is_int(source.get("generation")) and generation != source["generation"] + 1:
                problems.append(Problem("generation", "generation", "the generation must be one more than "
                                        "source.generation"))
    check_fields(data, LINEAGE_RULES, problems)
    for section, path, item, _ in walk_items(data):
        if section == "features" and isinstance(item.get("spec_dir"), str) and item["spec_dir"]:
            if path_problem(item["spec_dir"]) or not SPEC_DIR_PATTERN.match(item["spec_dir"]):
                problems.append(Problem("field", join(path, "spec_dir"), "must be a folder directly under specs/"))
    check_ids(data, problems, unique_with_discarded=True)
    check_ranges(data, generation, problems)
    check_code_blocks(data, problems)
    check_dependencies(data, problems)
    return sorted_problems(problems)


def load_lineage(path: Path) -> tuple[str, dict | None, list[Problem]]:
    """The state of a lineage.json (none, present, unreadable, newer, invalid, conflict), its content, its problems.

    Only this one file of .sdd-rebuild/ is ever opened.
    """
    if not path.exists():
        return "none", None, []
    try:
        data = read_json_object(path)
    except (Unreadable, OSError) as error:
        return "unreadable", None, [Problem("json", "", f"lineage.json {error}")]
    if data.get("tool") != LINEAGE_TOOL:
        return "conflict", None, []
    if schema_is_newer(data.get("schema")):
        return "newer", None, []
    problems = lineage_problems(data)
    # Like the nutrients: a lineage edited by hand to hold a secret is invalid, and only the paths are reported.
    check_secrets(data, problems)
    if problems:
        return "invalid", None, sorted_problems(problems)
    return "present", data, []


# -------------------------------------------------------------- read scope

# The read scope of data-model.md; names are compared in lowercase on every platform.
DEPENDENCY_DIRS = frozenset({
    "node_modules", "bower_components", "jspm_packages", "vendor", ".venv", "venv", "pods", "carthage", ".terraform",
    ".bundle",
})
BUILD_DIRS = frozenset({
    "dist", "build", "target", "bin", "obj", "out", ".next", ".nuxt", ".svelte-kit", ".output", "coverage", "htmlcov",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".gradle", ".cache", ".parcel-cache",
    ".turbo", ".eggs",
})
BUILD_SUFFIX = ".egg-info"
TOOLING_DIRS = frozenset({".git", ".idea", ".vscode", ".claude", ".sdd-export", ".sdd-rebuild", ".specify"})
GENERATED_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json", "uv.lock", "poetry.lock",
    "pipfile.lock", "cargo.lock", "go.sum", "composer.lock", "gemfile.lock", "packages.lock.json",
})
GENERATED_SUFFIXES = (".min.js", ".min.css", ".map")
BINARY_SUFFIXES = (
    # images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".icns", ".webp", ".tif", ".tiff", ".psd", ".heic", ".avif",
    # audio and video
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".wmv",
    # fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # archives
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war", ".whl", ".nupkg",
    # executables and libraries
    ".exe", ".dll", ".so", ".dylib", ".a", ".lib", ".o", ".obj", ".class", ".pyc", ".pyo", ".wasm", ".bin", ".msi",
    ".dmg", ".iso", ".apk", ".ipa",
    # databases
    ".db", ".sqlite", ".sqlite3", ".mdb", ".accdb",
    # documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
)
LARGE_FILE = 1024 * 1024
MAX_FILES = 1500
MAX_BYTES = 10 * 1024 * 1024
SNIFF_BYTES = 8 * 1024
MANIFEST_NAMES = frozenset({
    "package.json", "pyproject.toml", "setup.py", "go.mod", "cargo.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "composer.json", "gemfile", "mix.exs", "pubspec.yaml",
})
MANIFEST_SUFFIXES = (".csproj", ".sln")
SKIPPED_KEYS = ("ignored", "dependency", "build", "tooling", "generated", "secret", "binary", "large")
ROOT_AREA = "."


def folder_category(name: str, top: bool) -> str | None:
    """The category that excludes a folder by its name, or None."""
    name = name.lower()
    if top and name in TOOLING_DIRS:
        return "tooling"
    if name in DEPENDENCY_DIRS:
        return "dependency"
    if name in BUILD_DIRS or name.endswith(BUILD_SUFFIX):
        return "build"
    return None


def excluded_folder(path: str, is_dir: bool = False) -> tuple[str, str] | None:
    """(category, folder) for the first folder of path that is excluded, or None.

    .specify/memory/constitution.md stays readable although .specify/ is tooling.
    """
    if path == CONSTITUTION_PATH:
        return None
    parts = path.split("/")
    folders = parts if is_dir else parts[:-1]
    for index, name in enumerate(folders):
        category = folder_category(name, index == 0)
        if category:
            return category, "/".join(parts[: index + 1])
    return None


def name_category(name: str) -> str | None:
    """The category that excludes a file by its name: secret, generated or binary; None otherwise."""
    lowered = name.lower()
    if is_secret_name(lowered):
        return "secret"
    if lowered in GENERATED_NAMES or lowered.endswith(GENERATED_SUFFIXES):
        return "generated"
    if lowered.endswith(BINARY_SUFFIXES):
        return "binary"
    return None


def excluded_category(path: str, is_dir: bool = False) -> str | None:
    """The category that excludes a path by its name alone, or None (a secret file is "secret")."""
    folder = excluded_folder(path, is_dir)
    if folder:
        return folder[0]
    if is_secret_path(path):
        return "secret"
    return None if is_dir else name_category(path.rsplit("/", 1)[-1])


def inside(root: Path, target: str) -> bool:
    try:
        Path(target).relative_to(os.path.realpath(root))
    except ValueError:
        return False
    return True


def file_category(root: Path, path: str) -> tuple[str | None, int]:
    """(category or None when readable, size) of one file; secret files are judged by name and never opened."""
    full = root / path
    if is_secret_path(path):
        return "secret", 0
    category = name_category(path.rsplit("/", 1)[-1])
    if category:
        return category, 0
    if full.is_symlink():
        target = os.path.realpath(full)
        if not inside(root, target) or os.path.isdir(target):
            return "ignored", 0
    try:
        size = full.stat().st_size
    except OSError:
        return "ignored", 0
    if size > LARGE_FILE:
        return "large", size
    with open(full, "rb") as handle:
        if b"\0" in handle.read(SNIFF_BYTES):
            return "binary", size
    return None, size


class Scan:
    """Every readable file of a project with its size, and every excluded file or folder with its category.

    Excluded folders (dependency, build, tooling) count once each; excluded files count one by one.
    """

    def __init__(self, root: Path):
        self.root = root
        self.readable: dict[str, int] = {}
        self.skipped: list[tuple[str, str]] = []
        listed = git_list(root, "--cached", "--others", "--exclude-standard") if is_git_repository(root) else None
        self.ignore_source = "none" if listed is None else "git"
        if listed is None:
            self._walk()
        else:
            self._from_git(listed)
        constitution = root / CONSTITUTION_PATH
        if CONSTITUTION_PATH not in self.readable and constitution.is_file() and not constitution.is_symlink():
            category, size = file_category(root, CONSTITUTION_PATH)
            if category is None:
                self.readable[CONSTITUTION_PATH] = size

    def _add_file(self, path: str) -> None:
        category, size = file_category(self.root, path)
        if category is None:
            self.readable[path] = size
        else:
            self.skipped.append((category, path))

    def _walk(self) -> None:
        for current, dirs, names in os.walk(self.root, followlinks=False):
            base = Path(current).relative_to(self.root).as_posix()
            prefix = "" if base == "." else base + "/"
            descend = []
            for name in sorted(dirs):
                rel = prefix + name
                category = folder_category(name, top=not prefix)
                if (Path(current) / name).is_symlink():
                    self.skipped.append(("ignored", rel))
                elif category:
                    self.skipped.append((category, rel))
                else:
                    descend.append(name)
            dirs[:] = descend
            for name in sorted(names):
                self._add_file(prefix + name)

    def _from_git(self, listed: list[str]) -> None:
        folders: set[tuple[str, str]] = set()
        for path in sorted(set(listed)):
            full = self.root / path
            if not full.is_file() and not full.is_symlink():
                continue
            folder = excluded_folder(path)
            if folder:
                folders.add(folder)
                continue
            if full.is_symlink() and os.path.isdir(full):
                self.skipped.append(("ignored", path))
                continue
            self._add_file(path)
        self.skipped.extend(folders)
        ignored = git_list(self.root, "--others", "--ignored", "--exclude-standard", "--directory") or []
        self.skipped.extend(("ignored", entry.rstrip("/")) for entry in ignored)

    def within(self, scopes: list[str]) -> tuple[dict[str, int], list[tuple[str, str]]]:
        """The readable files and the exclusions under the scopes; no scopes means the whole project."""
        if not scopes:
            return dict(self.readable), list(self.skipped)

        def covered(path: str) -> bool:
            return any(path == scope or path.startswith(scope + "/") for scope in scopes)

        readable = {path: size for path, size in self.readable.items() if covered(path) or always_read(path)}
        return readable, [(category, path) for category, path in self.skipped if covered(path)]


def always_read(path: str) -> bool:
    """The constitution and every specs/<name>/spec.md: the sources of FR-005, read whatever the scope."""
    parts = path.split("/")
    return path == CONSTITUTION_PATH or (len(parts) == 3 and parts[0] == SPECS_DIR and parts[2] == "spec.md")


def summary_of(readable: dict[str, int], skipped: list[tuple[str, str]]) -> dict:
    """files, bytes, too_large, areas, skipped and secret_files of a set of readable files and exclusions."""
    areas: dict[str, dict] = {}
    for path, size in readable.items():
        head, _, rest = path.partition("/")
        name = head if rest else ROOT_AREA
        area = areas.setdefault(name, {"path": name, "files": 0, "bytes": 0, "manifests": []})
        area["files"] += 1
        area["bytes"] += size
        leaf = rest if rest else head
        if "/" not in leaf and (leaf.lower() in MANIFEST_NAMES or leaf.lower().endswith(MANIFEST_SUFFIXES)):
            area["manifests"].append(leaf)
    ordered_areas = sorted((a for a in areas.values() if a["path"] != ROOT_AREA), key=lambda a: a["path"])
    if ROOT_AREA in areas:
        ordered_areas.append(areas[ROOT_AREA])
    for area in ordered_areas:
        area["manifests"].sort()
    count, total = len(readable), sum(readable.values())
    with_manifests = sum(1 for area in ordered_areas if area["manifests"])
    counts = {key: 0 for key in SKIPPED_KEYS}
    for category, _ in skipped:
        counts[category] += 1
    return {
        "files": count,
        "bytes": total,
        "too_large": count > MAX_FILES or total > MAX_BYTES or with_manifests >= 2,
        "areas": ordered_areas,
        "skipped": counts,
        "secret_files": sorted(path for category, path in skipped if category == "secret"),
    }


def read_scope(root: Path, scopes: list[str] | None = None) -> dict:
    """The readable files of root (under scopes, when given), how many paths each rule excluded, and the secret files.

    Paths are relative and slash-separated; secret files are listed by path and never opened.
    """
    scan = Scan(root)
    readable, skipped = scan.within(scopes or [])
    summary = summary_of(readable, skipped)
    return {**summary, "ignore_source": scan.ignore_source, "readable": dict(sorted(readable.items())), "scan": scan}


def scope_problem(root: Path, scan: Scan, scope: str) -> str | None:
    """Why a --scope path cannot be used, or None."""
    problem = path_problem(scope)
    if problem:
        return f"the scope {scope!r} {problem}"
    target = root / scope
    if not target.exists() and not target.is_symlink():
        return f"the scope {scope!r} does not exist in the project"
    if not inside(root, os.path.realpath(target)):
        return f"the scope {scope!r} is outside the project"
    is_dir = target.is_dir()
    category = excluded_category(scope, is_dir)
    if category is None and not is_dir and scope not in scan.readable:
        category = next((c for c, path in scan.skipped if path == scope), "excluded")
    if category is None and any(c == "ignored" and (scope == p or scope.startswith(p + "/")) for c, p in scan.skipped):
        category = "ignored"
    if category:
        return f"the scope {scope!r} is excluded from reading ({category})"
    return None


def normalized_scope(scope: str) -> str:
    scope = scope.replace("\\", "/") if os.sep == "\\" else scope
    while scope.endswith("/") and len(scope) > 1:
        scope = scope[:-1]
    return scope


def inventory_of(root: Path) -> dict:
    """The read scope of the whole project as `check` reports it: numbers only, no file list."""
    scope = read_scope(root)
    return {key: scope[key] for key in ("files", "bytes", "too_large", "ignore_source", "areas", "skipped", "secret_files")}


# ------------------------------------------------------------ project state

STATE_REASONS = {
    "conflict": "conflict", "unreadable": "nutrients-unreadable", "invalid": "nutrients-invalid",
    "newer": "nutrients-newer",
}
LINEAGE_REASONS = {
    "unreadable": "lineage-unreadable", "invalid": "lineage-invalid", "newer": "lineage-newer",
    "conflict": "lineage-conflict",
}
STATE_ERRORS = {
    "nutrients-unreadable": ".sdd-export/nutrients.json cannot be read; fix or remove it, nothing was written",
    "nutrients-invalid": ".sdd-export/nutrients.json does not match the nutrients format; fix it, nothing was written",
    "nutrients-newer": ".sdd-export/nutrients.json comes from a newer sdd-export; update the skill, nothing was written",
    "lineage-unreadable": ".sdd-rebuild/lineage.json cannot be read; fix it, nothing was written",
    "lineage-invalid": ".sdd-rebuild/lineage.json does not match the lineage format; fix it, nothing was written",
    "lineage-newer": ".sdd-rebuild/lineage.json comes from a newer sdd-rebuild; update the skill, nothing was written",
    "lineage-conflict": ".sdd-rebuild/lineage.json was not written by sdd-rebuild; nothing was written",
}


def spec_entries(root: Path) -> list[str]:
    folder = root / SPECS_DIR
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and not p.is_symlink() and (p / "spec.md").is_file())


def project_state(root: Path, inventory: bool) -> dict:
    """Everything `check` reports, plus reason, error and problems when the project cannot be exported."""
    writable_target = root / EXPORT_DIR if (root / EXPORT_DIR).is_dir() else root
    state: dict = {
        "project": root.name,
        "git": is_git_repository(root),
        "writable": os.access(writable_target, os.W_OK),
    }
    folder = export_folder(root)
    state.update({key: folder[key] for key in ("export_dir", "nutrients", "view", "view_secret_lines", "gitattributes",
                                               "state")})
    nulls = {"lineage": None, "generation": None, "existing_generation": None, "constitution": None, "specs": None,
             "lineage_missing_specs": None, "inventory": None, "existing": None, "lineage_content": None}
    if folder["export_dir"] == "conflict":
        return {**state, **nulls, "conflicts": folder["conflicts"], "reason": "conflict", "problems": []}
    lineage_status, lineage, lineage_problems = load_lineage(root / LINEAGE_PATH)
    existing = folder["existing"]
    names = spec_entries(root)
    lineage_dirs = {}
    if lineage:
        lineage_dirs = {f.get("spec_dir"): f.get("id") for f in lineage.get("features", []) if isinstance(f, dict)}
    state.update({
        "lineage": lineage_status,
        "generation": lineage["generation"] if lineage_status == "present" else (1 if lineage_status == "none" else None),
        "existing_generation": existing.get("generation") if existing else None,
        "constitution": CONSTITUTION_PATH if (root / CONSTITUTION_PATH).is_file() else None,
        "specs": [{"dir": f"{SPECS_DIR}/{name}", "spec": f"{SPECS_DIR}/{name}/spec.md",
                   "in_lineage": f"{SPECS_DIR}/{name}" in lineage_dirs} for name in names],
        "lineage_missing_specs": [{"id": feature_id, "spec_dir": spec_dir} for spec_dir, feature_id in lineage_dirs.items()
                                  if f"{spec_dir}" not in {f"{SPECS_DIR}/{n}" for n in names}],
        "inventory": None,
        "existing": existing,
        "lineage_content": lineage,
    })
    reason = STATE_REASONS.get(folder["export_dir"]) or LINEAGE_REASONS.get(lineage_status)
    problems = folder["errors"] if folder["export_dir"] == "invalid" else lineage_problems
    if reason is None and inventory:
        state["inventory"] = inventory_of(root)
    return {**state, "reason": reason, "problems": problems}


def state_failure(io, state: dict, extra: dict | None = None) -> int:
    """Exit code 3 with the reason the project cannot be exported now."""
    reason = state["reason"]
    fields = dict(extra or {})
    if reason == "conflict":
        fields["conflicts"] = state["conflicts"]
    if state["problems"]:
        fields["errors"] = [problem.as_dict() for problem in state["problems"]]
    message = CONFLICT if reason == "conflict" else STATE_ERRORS[reason]
    return io.fail(message, reason, EXIT_STATE, **fields)


# ------------------------------------------------------------------ commands


def command_check(io, project: Path, options: dict) -> int:
    state = project_state(project, inventory=True)
    out = {key: state[key] for key in CHECK_KEYS}
    if state["reason"] is None:
        return io.emit(out)
    return state_failure(io, state, out)


CHECK_KEYS = (
    "project", "git", "writable", "export_dir", "nutrients", "view", "view_secret_lines", "gitattributes", "state",
    "lineage", "generation", "existing_generation", "constitution", "specs", "lineage_missing_specs", "inventory", "existing", "lineage_content",
)


def read_draft(io) -> tuple[object, list[Problem]]:
    data = io.stdin.read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    if data.startswith(b"\xef\xbb\xbf"):
        return None, [Problem("json", "", "the draft starts with a byte order mark")]
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, [Problem("json", "", "the draft is not valid JSON in UTF-8")]
    if not isinstance(value, dict):
        return None, [Problem("json", "", "the draft must be a JSON object")]
    return value, []


def checked_draft(io, project: Path, state: dict) -> tuple[object, list[Problem], dict]:
    """Read and validate the draft; also the output fields ok, errors, counts and diff."""
    draft, problems = read_draft(io)
    lineage = state["lineage_content"]
    if not problems:
        problems = validate_draft(draft, lineage, state["existing"], project)
    generation = draft.get("generation") if isinstance(draft, dict) else None
    out = {
        "ok": not problems,
        "errors": [problem.as_dict() for problem in problems],
        "counts": counts_of(draft, generation) if isinstance(draft, dict) and not has_field_problems(problems) else None,
        # No diff while a secret is reported: the diff repeats the draft's text.
        "diff": None if draft is None or has_field_problems(problems) or any(p.secret for p in problems)
        else compute_diff(state["existing"], draft),
    }
    return draft, problems, out


def draft_failure(io, problems: list[Problem], out: dict) -> int:
    if any(problem.secret for problem in problems):
        return io.fail(SECRET, "secret", EXIT_FAILED, **out)
    return io.fail(INVALID, "invalid", EXIT_FAILED, **out)


def command_validate(io, project: Path, options: dict) -> int:
    state = project_state(project, inventory=False)
    if state["reason"] is not None:
        return state_failure(io, state)
    _, problems, out = checked_draft(io, project, state)
    if problems:
        return draft_failure(io, problems, out)
    return io.emit(out)


def command_files(io, project: Path, options: dict) -> int:
    state = project_state(project, inventory=False)
    if state["reason"] is not None:
        return state_failure(io, state)
    scopes = sorted({normalized_scope(scope) for scope in options["scope"]})
    scan = Scan(project)
    for scope in scopes:
        problem = scope_problem(project, scan, scope)
        if problem:
            return io.fail(problem, "usage", EXIT_FAILED)
    readable, skipped = scan.within(scopes)
    summary = summary_of(readable, skipped)
    files = [] if summary["too_large"] else [{"path": path, "bytes": size} for path, size in sorted(readable.items())]
    hits = []
    for entry in files:
        hits.extend({"path": entry["path"], "line": line} for line in scan_file(project / entry["path"]))
    return io.emit({
        "scope": scopes,
        "too_large": summary["too_large"],
        "files": files,
        "secret_hits": hits,
        "skipped": summary["skipped"],
        "secret_files": summary["secret_files"],
    })


def write_temporary(folder: Path, name: str, data: bytes, temporaries: list[Path]) -> Path:
    path = folder / f".{name}.tmp-{random_names.token_hex(8)}"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
    temporaries.append(path)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    return path


def cleanup_after_failure(temporaries: list[Path], folder: Path, created: bool) -> None:
    """Remove this run's temporary files, and the export folder when this run created it and it is empty."""
    for path in temporaries:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    try:
        if created and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass


def command_write(io, project: Path, options: dict) -> int:
    state = project_state(project, inventory=False)
    if state["reason"] is not None:
        return state_failure(io, state)
    if state["state"] != options["expect"]:
        return io.fail(CHANGED, "changed", EXIT_FAILED)
    draft, problems, out = checked_draft(io, project, state)
    if problems:
        return draft_failure(io, problems, out)
    nutrients = ordered({**draft, "tool": TOOL, "schema": SCHEMA, "exported_at": utc_today()}, "nutrients")
    nutrients_bytes = serialize(nutrients, "nutrients")
    readme_bytes = render_readme(nutrients)
    folder = project / EXPORT_DIR
    created = False
    temporaries: list[Path] = []
    written: list[str] = []
    try:
        if not folder.is_dir():
            folder.mkdir()
            created = True
        new_nutrients = write_temporary(folder, NUTRIENTS_NAME, nutrients_bytes, temporaries)
        new_readme = write_temporary(folder, README_NAME, readme_bytes, temporaries)
        os.replace(new_nutrients, folder / NUTRIENTS_NAME)
        written.append(f"{EXPORT_DIR}/{NUTRIENTS_NAME}")
        os.replace(new_readme, folder / README_NAME)
        written.append(f"{EXPORT_DIR}/{README_NAME}")
        if not (folder / GITATTRIBUTES_NAME).exists():
            new_attributes = write_temporary(folder, GITATTRIBUTES_NAME, GITATTRIBUTES.encode("utf-8"), temporaries)
            os.replace(new_attributes, folder / GITATTRIBUTES_NAME)
            written.append(f"{EXPORT_DIR}/{GITATTRIBUTES_NAME}")
    except OSError as error:
        cleanup_after_failure(temporaries, folder, created)
        return io.fail(COULD_NOT_WRITE.format(error.strerror or error), "os-error", EXIT_FAILED)
    return io.emit({
        "written": written,
        "created": created,
        "state": edit_state(folder)["state"],
        "generation": nutrients["generation"],
        "counts": out["counts"],
        "diff": out["diff"],
    })


# --------------------------------------------------------------------- main


class Usage(Exception):
    pass


class Io:
    def __init__(self, cwd: Path, stdin, stdout, stderr):
        self.cwd = cwd
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def emit(self, data: dict, code: int = EXIT_OK) -> int:
        self.stdout.write(dumps(data))
        if "error" in data:
            self.stderr.write((data["error"] + "\n").encode("utf-8"))
        return code

    def fail(self, message: str, reason: str, code: int = EXIT_FAILED, **fields) -> int:
        return self.emit({**fields, "error": message, "reason": reason}, code)


def parse_args(argv: list[str]) -> tuple[str, dict]:
    if not argv or argv[0] not in COMMANDS:
        raise Usage()
    command, rest = argv[0], argv[1:]
    allowed = {"--project"}
    if command == "files":
        allowed.add("--scope")
    if command == "write":
        allowed.add("--expect")
    options: dict = {"project": None, "scope": [], "expect": None}
    index = 0
    while index < len(rest):
        word = rest[index]
        name, has_value, value = word.partition("=")
        if name not in allowed:
            raise Usage()
        if not has_value:
            if index + 1 >= len(rest):
                raise Usage()
            index += 1
            value = rest[index]
        if name == "--scope":
            options["scope"].append(value)
        elif options[name[2:]] is not None:
            raise Usage()
        else:
            options[name[2:]] = value
        index += 1
    if command == "write" and options["expect"] is None:
        raise Usage()
    return command, options


def main(argv: list[str] | None = None, root: Path | None = None, stdin=None, stdout=None, stderr=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    io = Io(
        Path(root) if root is not None else Path.cwd(),
        stdin if stdin is not None else sys.stdin.buffer,
        stdout if stdout is not None else sys.stdout.buffer,
        stderr if stderr is not None else sys.stderr.buffer,
    )
    try:
        command, options = parse_args(argv)
    except Usage:
        io.stderr.write((USAGE + "\n").encode("utf-8"))
        return io.emit({"error": USAGE, "reason": "usage"}, EXIT_FAILED)
    project = io.cwd if options["project"] is None else io.cwd / options["project"]
    if not project.is_dir():
        return io.fail(NOT_A_FOLDER, "project", EXIT_STATE)
    return HANDLERS[command](io, project.resolve(), options)


HANDLERS = {"check": command_check, "files": command_files, "validate": command_validate, "write": command_write}


if __name__ == "__main__":
    sys.exit(main())
