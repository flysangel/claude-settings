"""Helpers shared by the bootstrap-script tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

HOME_FILES = {
    "CLAUDE.md": "# Global preferences\n",
    "skills/sdd-init/SKILL.md": "init\n",
}


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def make_source_repo(root: Path) -> Path:
    """A git repository holding the real tools/ and a small home/."""
    repo = root / "source"
    shutil.copytree(REPO_ROOT / "tools", repo / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    # Same line-ending rules as the real repository, so a Windows clone keeps LF.
    shutil.copy(REPO_ROOT / ".gitattributes", repo / ".gitattributes")
    for rel, content in HOME_FILES.items():
        path = repo / "home" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    git(repo, "init", "--quiet")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "init")
    return repo


def commit_change(repo: Path, rel: str, content: str) -> None:
    (repo / "home" / rel).write_bytes(content.encode("utf-8"))
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "change")


def base_env(home: Path, repo: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    # Keep uv's cache outside the temporary home so runs stay fast.
    cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
    env["UV_CACHE_DIR"] = cache
    env.pop("CLAUDE_SETTINGS_REPO", None)
    if repo is not None:
        env["CLAUDE_SETTINGS_REPO"] = str(repo)
    return env
