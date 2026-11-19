# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deploy the contents of home/ into ~/.claude.

Usage:
    uv run tools/deploy.py                   install or update
    uv run tools/deploy.py --replace         install or update, replacing conflicting files (backed up first)
    uv run tools/deploy.py remove            remove what this tool installed and restore backups
    uv run tools/deploy.py remove --replace  remove, setting aside files modified since install

Exit codes: 0 success, 1 failure, 2 conflicts (nothing written), 3 missing prerequisites.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFLICT = 2
EXIT_MISSING = 3

SCHEMA = 1
STATE_DIR = ".claude-settings"
IGNORED_NAMES = {".gitkeep"}

USAGE = "usage: deploy.py [--replace] | remove [--replace]"


class DeployError(Exception):
    """A failure that should be reported to the user with exit code 1."""


# ---------------------------------------------------------------- helpers


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def emit(action: str, text: str) -> None:
    print(f"{action:<9} {text}")


def scan_source(source: Path) -> dict[str, bytes]:
    """Return every deployable file under source, keyed by POSIX relative path."""
    if not source.is_dir():
        raise DeployError(f"deploy source not found: {source}")
    files: dict[str, bytes] = {}
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.name not in IGNORED_NAMES:
            files[path.relative_to(source).as_posix()] = path.read_bytes()
    return files


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".claude-settings-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def repo_commit(source: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


# --------------------------------------------------------------- manifest


class Manifest:
    """What this tool installed. Holds relative paths and hashes only."""

    def __init__(self) -> None:
        self.exists = False
        self.status = "complete"
        self.repo_commit = ""
        # path -> {"sha256": str, "backup": bool, "previous": str | None}
        self.entries: dict[str, dict] = {}
        self.created_dirs: list[str] = []

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        manifest = cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = {}
            for item in raw["entries"]:
                entries[str(item["path"])] = {
                    "sha256": str(item["sha256"]),
                    "backup": bool(item.get("backup", False)),
                    "previous": item.get("previous"),
                }
            manifest.status = str(raw.get("status", "complete"))
            manifest.repo_commit = str(raw.get("repo_commit", ""))
            manifest.created_dirs = [str(d) for d in raw.get("created_dirs", [])]
            manifest.entries = entries
            manifest.exists = True
        except (OSError, ValueError, KeyError, TypeError):
            # Missing or unreadable: we cannot prove ownership of anything.
            return cls()
        return manifest

    def to_json(self) -> str:
        entries = []
        for path in sorted(self.entries):
            entry = self.entries[path]
            item = {"path": path, "sha256": entry["sha256"], "backup": entry["backup"]}
            if entry.get("previous"):
                item["previous"] = entry["previous"]
            entries.append(item)
        data = {
            "schema": SCHEMA,
            "status": self.status,
            "repo_commit": self.repo_commit,
            "entries": entries,
            "created_dirs": sorted(set(self.created_dirs)),
        }
        return json.dumps(data, indent=2) + "\n"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, self.to_json().encode("utf-8"))

    def owns(self, path: str, current_hash: str) -> bool:
        """True when the file on disk is exactly what this tool last put there."""
        entry = self.entries.get(path)
        if entry is None:
            return False
        return current_hash in (entry["sha256"], entry.get("previous"))


# ------------------------------------------------------------------ paths


class Layout:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.state = target / STATE_DIR
        self.manifest = self.state / "manifest.json"
        self.backups = self.state / "backups"
        self.discarded = self.state / "discarded"

    def file(self, rel: str) -> Path:
        return self.target.joinpath(*rel.split("/"))

    def backup(self, rel: str) -> Path:
        return self.backups.joinpath(*rel.split("/"))

    def rel(self, path: Path) -> str:
        return path.relative_to(self.target).as_posix()


def missing_dirs(layout: Layout, rels: list[str]) -> list[str]:
    """Directories (relative, '.' for the target itself) that must be created."""
    needed: set[str] = set()
    for rel in rels:
        parent = layout.file(rel).parent
        while True:
            if parent.exists():
                break
            needed.add("." if parent == layout.target else layout.rel(parent))
            if parent == layout.target:
                break
            parent = parent.parent
    return sorted(needed)


def prune_dirs(layout: Layout, created_dirs: list[str]) -> list[str]:
    """Remove created directories that are now empty. Returns the ones still present."""
    remaining = []
    for rel in sorted(set(created_dirs), key=lambda d: (-d.count("/"), d)):
        if rel == ".":
            remaining.append(rel)
            continue
        path = layout.file(rel)
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
        elif path.exists():
            remaining.append(rel)
    return remaining


def already_restored(layout: Layout, entry: dict, rel: str) -> bool:
    """A backed-up original was put back by an interrupted earlier run."""
    return bool(entry.get("backup")) and not layout.backup(rel).exists()


def set_aside(layout: Layout, rel: str, stamp: str) -> None:
    """Move a user-modified file out of the way so nothing is lost."""
    dest = layout.discarded.joinpath(stamp, *rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(layout.file(rel), dest)
    emit("discarded", f"{rel} -> {layout.rel(dest)}")


def restore_backup(layout: Layout, rel: str) -> None:
    backup = layout.backup(rel)
    if backup.exists():
        dest = layout.file(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(backup, dest)
        emit("restored", rel)


def report_conflicts(conflicts: list[tuple[str, str]]) -> int:
    for rel, reason in conflicts:
        emit("conflict", f"{rel} ({reason})")
    count = len(conflicts)
    noun = "conflict" if count == 1 else "conflicts"
    print(
        f"{count} {noun}. Nothing was written. "
        "Re-run with --replace to overwrite (originals are backed up)."
    )
    return EXIT_CONFLICT


FOREIGN = "not installed by this tool"
MODIFIED = "modified since install"


# ---------------------------------------------------------------- install


def plan_install(layout: Layout, source: dict[str, bytes], manifest: Manifest) -> dict[str, str]:
    """Classify every path without touching the disk. See data-model.md."""
    plan: dict[str, str] = {}
    for rel, data in source.items():
        path = layout.file(rel)
        if path.is_dir():
            raise DeployError(f"a directory is in the way of a file: {rel}")
        if not path.exists():
            plan[rel] = "create"
            continue
        current = sha256_file(path)
        wanted = sha256_bytes(data)
        if current == wanted:
            plan[rel] = "keep" if rel in manifest.entries else "adopt"
        elif manifest.owns(rel, current):
            plan[rel] = "update"
        elif rel in manifest.entries:
            plan[rel] = "conflict-modified"
        else:
            plan[rel] = "conflict-foreign"
    for rel, entry in manifest.entries.items():
        if rel in source:
            continue
        path = layout.file(rel)
        if not path.is_file():
            plan[rel] = "forget"
        elif manifest.owns(rel, sha256_file(path)):
            plan[rel] = "delete"
        elif already_restored(layout, entry, rel):
            plan[rel] = "forget"
        else:
            plan[rel] = "conflict-modified"
    return plan


def install(layout: Layout, source_dir: Path, replace: bool) -> int:
    source = scan_source(source_dir)
    manifest = Manifest.load(layout.manifest)
    plan = plan_install(layout, source, manifest)

    conflicts = [
        (rel, FOREIGN if action == "conflict-foreign" else MODIFIED)
        for rel, action in sorted(plan.items())
        if action.startswith("conflict-")
    ]
    if conflicts and not replace:
        return report_conflicts(conflicts)

    # The state we are aiming for.
    final = Manifest()
    final.exists = True
    final.repo_commit = manifest.repo_commit
    for rel, data in source.items():
        old = manifest.entries.get(rel, {})
        final.entries[rel] = {
            "sha256": sha256_bytes(data),
            "backup": bool(old.get("backup")) or plan[rel] == "conflict-foreign",
            "previous": None,
        }
    writes = [rel for rel in source if plan[rel] not in ("keep", "adopt")]
    final.created_dirs = sorted(set(manifest.created_dirs) | set(missing_dirs(layout, writes)))

    changing = [rel for rel, action in plan.items() if action not in ("keep", "forget")]
    unchanged = (
        manifest.exists
        and manifest.status == "complete"
        and not changing
        and {r: e["sha256"] for r, e in manifest.entries.items()}
        == {r: e["sha256"] for r, e in final.entries.items()}
    )
    if unchanged or (not manifest.exists and not source):
        print("Already up to date.")
        return EXIT_OK

    # Journal first: an interrupted run can be finished by running again.
    journal = Manifest()
    journal.exists = True
    journal.status = "applying"
    journal.repo_commit = manifest.repo_commit
    journal.created_dirs = final.created_dirs
    for rel, entry in final.entries.items():
        path = layout.file(rel)
        previous = sha256_file(path) if path.is_file() else None
        journal.entries[rel] = {**entry, "previous": previous}
    for rel, action in plan.items():
        if action in ("delete", "conflict-modified") and rel not in source:
            journal.entries[rel] = dict(manifest.entries[rel])
    journal.save(layout.manifest)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    counts = {"created": 0, "updated": 0, "adopted": 0, "deleted": 0}

    for rel in sorted(plan):
        action = plan[rel]
        path = layout.file(rel)
        if rel in source:
            if action == "keep":
                continue
            if action == "adopt":
                emit("adopted", rel)
                counts["adopted"] += 1
                continue
            if action == "conflict-foreign":
                backup = layout.backup(rel)
                if not backup.exists():  # keep the first original only
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, backup)
                emit("backup", f"{rel} -> {layout.rel(backup)}")
            elif action == "conflict-modified":
                set_aside(layout, rel, stamp)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(path, source[rel])
            if action == "create":
                emit("created", rel)
                counts["created"] += 1
            else:
                emit("updated", rel)
                counts["updated"] += 1
        else:
            if action == "forget":
                continue
            if action == "conflict-modified":
                set_aside(layout, rel, stamp)
            else:
                path.unlink()
            emit("deleted", rel)
            counts["deleted"] += 1
            restore_backup(layout, rel)

    final.created_dirs = prune_dirs(layout, final.created_dirs)
    final.repo_commit = repo_commit(source_dir)
    final.save(layout.manifest)

    summary = ", ".join(f"{count} {name}" for name, count in counts.items() if count)
    print(f"Installed: {summary}." if summary else "Installed.")
    return EXIT_OK


# ----------------------------------------------------------------- remove


def remove(layout: Layout, replace: bool) -> int:
    manifest = Manifest.load(layout.manifest)
    if not manifest.exists:
        print("Nothing to remove.")
        return EXIT_OK

    plan: dict[str, str] = {}
    for rel, entry in manifest.entries.items():
        path = layout.file(rel)
        if not path.is_file():
            plan[rel] = "gone"
        elif manifest.owns(rel, sha256_file(path)):
            plan[rel] = "delete"
        elif already_restored(layout, entry, rel):
            plan[rel] = "gone"
        else:
            plan[rel] = "conflict-modified"

    conflicts = [(rel, MODIFIED) for rel, action in sorted(plan.items()) if action.startswith("conflict-")]
    if conflicts and not replace:
        return report_conflicts(conflicts)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    removed = 0
    for rel in sorted(plan):
        action = plan[rel]
        if action == "conflict-modified":
            set_aside(layout, rel, stamp)
        elif action == "delete":
            layout.file(rel).unlink()
        if action != "gone":
            emit("deleted", rel)
            removed += 1
        restore_backup(layout, rel)

    prune_dirs(layout, manifest.created_dirs)
    layout.manifest.unlink(missing_ok=True)
    if layout.backups.exists():
        shutil.rmtree(layout.backups)
    kept_discarded = layout.discarded.exists() and any(layout.discarded.rglob("*"))
    if layout.discarded.exists() and not kept_discarded:
        shutil.rmtree(layout.discarded)
    if layout.state.is_dir() and not any(layout.state.iterdir()):
        layout.state.rmdir()
    if "." in manifest.created_dirs and layout.target.is_dir() and not any(layout.target.iterdir()):
        layout.target.rmdir()

    print(f"Removed {removed} {'file' if removed == 1 else 'files'}.")
    if kept_discarded:
        print(f"Modified files were kept in {layout.rel(layout.discarded)}.")
    return EXIT_OK


# ------------------------------------------------------------------- main


def main(argv: list[str] | None = None, source: Path | None = None, target: Path | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    replace = "--replace" in args
    rest = [a for a in args if a != "--replace"]
    if rest not in ([], ["remove"]) or args.count("--replace") > 1:
        print(USAGE, file=sys.stderr)
        return EXIT_FAILURE

    source = source or Path(__file__).resolve().parent.parent / "home"
    layout = Layout(target or Path.home() / ".claude")
    try:
        if rest == ["remove"]:
            return remove(layout, replace)
        return install(layout, source, replace)
    except (DeployError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
