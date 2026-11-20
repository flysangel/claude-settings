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
    return io.fail(f"{argv[0]} is not implemented yet")


if __name__ == "__main__":
    sys.exit(main())
