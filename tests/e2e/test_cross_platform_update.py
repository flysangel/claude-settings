"""Cross-platform exchange: a project updated on one platform is used on the other.

Runs only in the CI jobs that set SDD_CROSS_PLATFORM (see .github/workflows/ci.yml),
next to tests/e2e/test_cross_platform.py and with the same variables:

- SDD_CROSS_PLATFORM=produce  bring Spec Kit 1.2.6 into a new repository with
  sdd-init and commit it; delete one .sh and commit; change one template and
  commit; run sdd-update; commit everything. Then write a git bundle, a sorted
  file list with modes and sdd-update's output into SDD_CROSS_PLATFORM_OWN.
- SDD_CROSS_PLATFORM=verify   clone the bundle the *other* platform wrote
  (SDD_CROSS_PLATFORM_OTHER), run Spec Kit's scripts in it without any extra step,
  and compare the file list and sdd-update's output with this platform's.

Needs the network, like tests/integration.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import GIT_IDENTITY, init_with_version, real_run_env, run_sdd_update, run_spec_kit_scripts

MODE_VARIABLE = "SDD_CROSS_PLATFORM"
MODE = os.environ.get(MODE_VARIABLE, "")
START = "1.2.6"
BUNDLE = "update.bundle"
FILE_LIST = "update-files.txt"
OUTPUT = "update-output.txt"
GONE = ".specify/scripts/bash/setup-plan.sh"
CHANGED = ".specify/templates/plan-template.md"

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        MODE not in ("produce", "verify"),
        reason=f"runs only in the CI cross-platform jobs, which set {MODE_VARIABLE}",
    ),
]


def directory(variable: str) -> Path:
    value = os.environ.get(variable)
    assert value, f"{variable} must be set when {MODE_VARIABLE}={MODE}"
    return Path(value)


def git(cwd: Path, env: dict, *args: str) -> str:
    done = subprocess.run(["git", *GIT_IDENTITY, *args], cwd=cwd, env=env, capture_output=True)
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    return done.stdout.decode("utf-8")


def file_list(repo: Path, env: dict) -> str:
    """Mode and path of every committed file, sorted by path, one per line."""
    rows = []
    for row in git(repo, env, "ls-tree", "-r", "HEAD").splitlines():
        meta, path = row.split("\t", 1)
        rows.append((path, meta.split(" ")[0]))
    return "".join(f"{mode} {path}\n" for path, mode in sorted(rows))


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "fake-home"
    home.mkdir()
    result = real_run_env(home)
    # sdd-init runs in this process below and starts the official tool with this process's environment.
    for key in ("HOME", "USERPROFILE", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR"):
        monkeypatch.setenv(key, result[key])
    return result


@pytest.mark.skipif(MODE != "produce", reason=f"{MODE_VARIABLE} is not 'produce'")
def test_produce_updated_bundle(tmp_path, env, sdd_init, capsys):
    out_dir = directory("SDD_CROSS_PLATFORM_OWN")
    out_dir.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "project"
    repo.mkdir()
    git(repo, env, "init", "--quiet")

    assert init_with_version(sdd_init, repo, START, sdd_init.run_official_tool) == 0, capsys.readouterr()
    capsys.readouterr()
    git(repo, env, "add", "-A")
    git(repo, env, "commit", "--quiet", "-m", f"spec kit {START}")
    (repo / GONE).unlink()
    git(repo, env, "add", "-A")
    git(repo, env, "commit", "--quiet", "-m", "remove a script")
    (repo / CHANGED).write_bytes((repo / CHANGED).read_bytes() + b"\n<!-- my change -->\n")
    git(repo, env, "add", "-A")
    git(repo, env, "commit", "--quiet", "-m", "change a template")

    done = run_sdd_update(repo, env)

    assert done.returncode == 0, done.stderr
    assert "\\" not in done.stdout
    assert f"staged    {GONE} (executable bit recorded in the git index)" in done.stdout
    assert f"kept      {CHANGED} (modified; new version: .specify/sdd-update/{CHANGED}.new)" in done.stdout

    git(repo, env, "add", "-A")
    git(repo, env, "commit", "--quiet", "-m", "update spec kit")
    git(repo, env, "bundle", "create", str(out_dir / BUNDLE), "--all")
    listing = file_list(repo, env)
    (out_dir / FILE_LIST).write_bytes(listing.encode("utf-8"))
    (out_dir / OUTPUT).write_bytes(done.stdout.encode("utf-8"))

    scripts = [row for row in listing.splitlines() if row.endswith(".sh")]
    assert f"100755 {GONE}" in scripts
    assert scripts and all(row.startswith("100755 ") for row in scripts)
    assert all(row.startswith("100644 ") for row in listing.splitlines() if not row.endswith(".sh"))


@pytest.mark.skipif(MODE != "verify", reason=f"{MODE_VARIABLE} is not 'verify'")
def test_verify_updated_bundle_from_the_other_platform(tmp_path, env):
    other = directory("SDD_CROSS_PLATFORM_OTHER")
    own = directory("SDD_CROSS_PLATFORM_OWN")
    clone = tmp_path / "clone"
    # Git for Windows converts line endings by default; set it explicitly so the test does not depend on the runner.
    options = ["-c", "core.autocrlf=true"] if sys.platform == "win32" else []

    git(tmp_path, env, "clone", "--quiet", *options, str(other / BUNDLE), str(clone))

    scripts = sorted((clone / ".specify" / "scripts" / "bash").glob("*.sh"))
    assert scripts and (clone / GONE) in scripts
    for script in scripts:
        assert b"\r" not in script.read_bytes(), script.name
        if sys.platform != "win32":
            assert os.access(script, os.X_OK), script.name
    assert git(clone, env, "status", "--porcelain") == ""

    # No extra step between the clone and Spec Kit's own scripts.
    run_spec_kit_scripts(clone, env)

    theirs = (other / FILE_LIST).read_bytes().decode("utf-8")
    mine = (own / FILE_LIST).read_bytes().decode("utf-8")
    assert file_list(clone, env) == theirs
    assert theirs == mine
    assert (other / OUTPUT).read_bytes() == (own / OUTPUT).read_bytes()

    again = run_sdd_update(clone, env)
    assert again.returncode == 0, again.stderr
    assert "is already the latest stable release. Nothing changed." in again.stdout
