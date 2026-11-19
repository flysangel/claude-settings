"""End-to-end tests for tools/setup.ps1 (Windows)."""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from _common import HOME_FILES, REPO_ROOT, base_env, commit_change, make_source_repo

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="setup.ps1 is the Windows bootstrap")

SETUP = REPO_ROOT / "tools" / "setup.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh") or "powershell"


def run(env, *args):
    command = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SETUP), *args]
    return subprocess.run(command, env=env, capture_output=True, text=True)


def test_install_update_and_remove(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    repo = make_source_repo(tmp_path)
    env = base_env(home, repo)

    result = run(env)
    assert result.returncode == 0, result.stderr
    for rel, content in HOME_FILES.items():
        assert (home / ".claude" / rel).read_bytes() == content.encode("utf-8")
    assert (home / ".claude-settings" / ".git").is_dir()

    result = run(env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Already up to date."

    commit_change(repo, "CLAUDE.md", "# Changed\n")
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert "updated   CLAUDE.md" in result.stdout
    assert (home / ".claude" / "CLAUDE.md").read_bytes() == b"# Changed\n"

    result = run(env, "remove")
    assert result.returncode == 0, result.stderr
    assert not (home / ".claude").exists()


def test_conflict_exit_code_and_replace_are_passed_through(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_bytes(b"mine\n")
    env = base_env(home, make_source_repo(tmp_path))

    result = run(env)
    assert result.returncode == 2
    assert "conflict  CLAUDE.md (not installed by this tool)" in result.stdout
    assert (home / ".claude" / "CLAUDE.md").read_bytes() == b"mine\n"

    result = run(env, "--replace")
    assert result.returncode == 0, result.stderr
    assert (home / ".claude" / ".claude-settings" / "backups" / "CLAUDE.md").read_bytes() == b"mine\n"


def test_missing_commands_are_all_listed_and_nothing_is_written(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    env = base_env(home, make_source_repo(tmp_path))
    env["PATH"] = str(empty_bin)

    result = run(env)

    assert result.returncode == 3
    assert "missing   git" in result.stdout
    assert "missing   uv" in result.stdout
    assert not (home / ".claude").exists()
    assert not (home / ".claude-settings").exists()


def test_unreachable_repo_fails_without_writing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = base_env(home, tmp_path / "does-not-exist")

    result = run(env)

    assert result.returncode == 1
    assert not (home / ".claude").exists()
