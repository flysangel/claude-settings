"""Integration tests: sdd-update with the real PyPI and two real versions of the official tool.

Everything here needs the network. A network failure is a test failure, not a
skip; offline, run `pytest -m "not network"`. All work happens under tmp_path;
neither this repository's .specify/ nor the real ~/.claude is touched.

The starting point is Spec Kit 1.2.6, brought in through sdd-init's own entry
point with only the version lookup replaced (research.md R5). Between 1.2.6 and
the current release files were added, removed and changed. If PyPI ever pulls
1.2.6, these tests fail and the starting version has to be changed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import (
    GIT_IDENTITY,
    git_run,
    init_with_version,
    real_run_env,
    run_sdd_init,
    run_sdd_update,
    run_spec_kit_scripts,
    snapshot,
)

pytestmark = pytest.mark.network

START = "1.2.6"
RECORD = ".specify/sdd-init.json"
PROTECTED = ".specify/memory/"
# The official tool writes the time it ran into a few files (manifests, the workflow registry).
TIMESTAMP = re.compile(rb"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")


def latest_stable_on_pypi() -> str:
    """Looked up independently of the script under test."""
    with urllib.request.urlopen("https://pypi.org/pypi/specify-cli/json", timeout=30) as response:
        releases = json.loads(response.read().decode("utf-8"))["releases"]
    stable = [
        version
        for version, files in releases.items()
        if re.fullmatch(r"\d+(\.\d+)*", version) and any(not f.get("yanked") for f in files)
    ]
    return max(stable, key=lambda v: [int(n) for n in v.split(".")])


def snap(root: Path, with_mtime: bool = False) -> dict:
    return {
        k: v
        for k, v in snapshot(root, with_mtime=with_mtime).items()
        if k != ".git/" and not k.startswith(".git/")
    }


def spec_kit_files(root: Path) -> dict[str, bytes]:
    """Every file under .specify/ and .claude/, by path, except the record and the comparison copies."""
    result = {}
    for top in (".specify", ".claude"):
        for path in sorted((root / top).rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and rel != RECORD and not rel.startswith(".specify/sdd-update/"):
                result[rel] = path.read_bytes()
    return result


def without_timestamps(data: bytes) -> bytes:
    return TIMESTAMP.sub(b"<time>", data)


def status(root: Path) -> str:
    return git_run(root, "status", "--porcelain", "--untracked-files=all")


def ls_files(root: Path) -> dict[str, str]:
    return {row.split("\t")[1]: row.split(" ")[0] for row in git_run(root, "ls-files", "-s").splitlines()}


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "fake-home"
    home.mkdir()
    result = real_run_env(home)
    # The in-process sdd-init run below starts the official tool with this process's environment.
    for key in ("HOME", "USERPROFILE", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR"):
        monkeypatch.setenv(key, result[key])
    return result


def git(root: Path, env: dict, *args: str) -> str:
    done = subprocess.run(["git", *GIT_IDENTITY, *args], cwd=root, env=env, check=True, capture_output=True)
    return done.stdout.decode("utf-8")


@pytest.fixture
def old_project(tmp_path, env, sdd_init, capsys):
    """A git repository with Spec Kit 1.2.6 brought in by sdd-init and committed."""
    root = tmp_path / "project"
    root.mkdir()
    git(root, env, "init", "--quiet")
    assert init_with_version(sdd_init, root, START, sdd_init.run_official_tool) == 0, capsys.readouterr()
    capsys.readouterr()
    record = json.loads((root / RECORD).read_bytes())
    assert record["speckit_version"] == START
    git(root, env, "add", "-A")
    git(root, env, "commit", "--quiet", "-m", f"spec kit {START}")
    return root


def test_update_from_an_older_release_to_the_latest(old_project, env, tmp_path, sdd_init):
    root = old_project
    latest = latest_stable_on_pypi()
    assert latest != START
    memory_before = {k: v for k, v in snap(root).items() if k.startswith(PROTECTED)}

    started = time.monotonic()
    done = run_sdd_update(root, env)
    elapsed = time.monotonic() - started

    assert done.returncode == 0, done.stderr
    assert elapsed < 120, f"the update took {elapsed:.0f} seconds"
    out = done.stdout.splitlines()
    assert "\\" not in done.stdout
    counts = {action: len([l for l in out if l.startswith(action + " ")]) for action in ("updated", "created", "removed", "kept")}
    assert counts["kept"] == 0
    assert counts["updated"] > 0
    expected_summary = (
        f"Spec Kit updated from {START} to {latest}: {counts['updated']} updated, "
        f"{counts['created']} created, {counts['removed']} removed, 0 kept."
    )
    assert expected_summary in out
    record = json.loads((root / RECORD).read_bytes())
    assert record["speckit_version"] == latest and record["status"] == "complete"

    # The same files as a project brought in with the latest release directly.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    direct = run_sdd_init(fresh, env, "init")
    assert direct.returncode == 0, direct.stderr
    mine, theirs = spec_kit_files(root), spec_kit_files(fresh)
    assert sorted(mine) == sorted(theirs)
    for path in mine:
        if not path.startswith(PROTECTED):
            assert without_timestamps(mine[path]) == without_timestamps(theirs[path]), path
    assert {k: v for k, v in snap(root).items() if k.startswith(PROTECTED)} == memory_before

    # Every recorded hash matches the file.
    for entry in record["entries"]:
        assert sdd_init.content_hash((root / entry["path"]).read_bytes()) == entry["sha256"], entry["path"]

    git(root, env, "add", "-A")
    git(root, env, "commit", "--quiet", "-m", "update")
    for attempt in range(5):
        before, before_status = snap(root, with_mtime=True), status(root)
        again = run_sdd_update(root, env)
        assert again.returncode == 0, again.stderr
        assert again.stdout.splitlines() == [
            f"Spec Kit {latest} is already the latest stable release. Nothing changed."
        ], attempt
        assert snap(root, with_mtime=True) == before
        assert status(root) == before_status == ""

    run_spec_kit_scripts(root, env)


def test_update_keeps_changes_and_the_result_runs_in_a_clone_made_with_autocrlf(old_project, env, tmp_path):
    root = old_project
    gone = ".specify/scripts/bash/setup-plan.sh"
    changed = ".specify/templates/plan-template.md"
    (root / gone).unlink()
    git(root, env, "add", "-A")
    git(root, env, "commit", "--quiet", "-m", "remove a script")
    original = (root / changed).read_bytes()
    (root / changed).write_bytes(original + b"\n<!-- my change -->\n")
    git(root, env, "add", "-A")
    git(root, env, "commit", "--quiet", "-m", "change a template")
    constitution = (root / ".specify/memory/constitution.md").read_bytes()

    done = run_sdd_update(root, env)

    assert done.returncode == 0, done.stderr
    out = done.stdout.splitlines()
    copy = f".specify/sdd-update/{changed}.new"
    assert f"kept      {changed} (modified; new version: {copy})" in out
    assert f"created   {gone}" in out
    assert f"staged    {gone} (executable bit recorded in the git index)" in out
    assert out[-1].startswith("Next: ")
    assert (root / changed).read_bytes() == original + b"\n<!-- my change -->\n"
    assert (root / copy).is_file()
    assert (root / ".specify/memory/constitution.md").read_bytes() == constitution
    git(root, env, "add", "-A")
    git(root, env, "commit", "--quiet", "-m", "update")

    clone = tmp_path / "clone"
    git(tmp_path, env, "clone", "--quiet", "-c", "core.autocrlf=true", str(root), str(clone))

    scripts = sorted((clone / ".specify" / "scripts" / "bash").glob("*.sh"))
    names = {p.name for p in scripts}
    assert {"common.sh", "create-new-feature.sh", "setup-plan.sh"} <= names
    index = ls_files(clone)
    for script in scripts:
        assert b"\r" not in script.read_bytes(), script.name
        assert index[script.relative_to(clone).as_posix()] == "100755", script.name
    for path, mode in index.items():
        if path.startswith(".specify/scripts/") and not path.endswith(".sh"):
            assert mode == "100644", path
    assert b"\r\n" in (clone / ".specify" / "templates" / "spec-template.md").read_bytes()
    assert git_run(clone, "status", "--porcelain") == ""

    run_spec_kit_scripts(clone, env)
    assert (clone / "specs" / "001-demo" / "plan.md").is_file()
    assert os.path.isdir(clone / "specs" / "001-demo")
