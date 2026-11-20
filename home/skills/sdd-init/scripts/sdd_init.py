# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bring Spec Kit into the current project, or remove it again.

Usage:
    uv run sdd_init.py init
    uv run sdd_init.py remove
"""

from __future__ import annotations

import sys

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_MISSING_TOOLS = 3
EXIT_UNAVAILABLE = 4

USAGE = "usage: sdd_init.py {init|remove}"


def fetch_latest_version() -> str:
    raise NotImplementedError


def run_official_tool(version: str, dest) -> None:
    raise NotImplementedError


def main(argv=None, *, resolve_version=fetch_latest_version, run_official=run_official_tool) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("init", "remove"):
        print(USAGE, file=sys.stderr)
        return EXIT_FAILED
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
