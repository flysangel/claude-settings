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

# The same patterns as sdd-grill, copied rather than loaded across skills. Deliberately conservative:
# a safety net, not a replacement for the skill's instructions.
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


def not_yet(io: Io, project: Path, options: dict) -> int:
    return io.fail("not implemented yet", "usage")


HANDLERS = {"check": not_yet, "files": not_yet, "validate": not_yet, "write": not_yet}


if __name__ == "__main__":
    sys.exit(main())
