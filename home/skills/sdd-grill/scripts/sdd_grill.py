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

import json
import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
# 2 is reserved (it means "conflict" for the deploy tool); 4 is not used (no network).
EXIT_NO_SPECKIT = 3

COMMANDS = ("check", "save", "verify", "focus", "clear")
USAGE = "usage: sdd_grill.py check|save|verify|focus|clear"


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
