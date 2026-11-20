"""Integration tests: the real script, the real PyPI and the real official tool.

Everything here needs the network. A network failure is a test failure, not a
skip; offline, run `pytest -m "not network"`. All work happens under tmp_path.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import GIT_IDENTITY, git_run, real_run_env, run_sdd_init, run_spec_kit_scripts, snapshot

pytestmark = pytest.mark.network

RECORD = ".specify/sdd-init.json"


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


def status(root: Path) -> str:
    return git_run(root, "status", "--porcelain", "--untracked-files=all")


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "fake-home"
    home.mkdir()
    return real_run_env(home)


@pytest.fixture
def project(tmp_path, env):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=root, env=env, check=True, capture_output=True)
    return root


def git(root: Path, env: dict, *args: str) -> str:
    done = subprocess.run(["git", *GIT_IDENTITY, *args], cwd=root, env=env, check=True, capture_output=True)
    return done.stdout.decode("utf-8")


def test_init_brings_in_the_latest_stable_release(project, env):
    expected = latest_stable_on_pypi()

    started = time.monotonic()
    done = run_sdd_init(project, env, "init")
    elapsed = time.monotonic() - started

    assert done.returncode == 0, done.stderr
    assert elapsed < 120, f"init took {elapsed:.0f} seconds"
    out = done.stdout.splitlines()
    record = json.loads((project / RECORD).read_bytes().decode("utf-8"))
    assert record["speckit_version"] == expected
    assert record["status"] == "complete"
    created = [l.split()[1] for l in out if l.startswith("created ")]
    assert out[-4] == f"Spec Kit {expected} initialized: {len(created)} created, 0 skipped."
    assert out[-2:] == [
        "Next: run /sdd-grill to be questioned until the constitution and specs are decided.",
        "Or use Spec Kit directly: run /speckit-constitution, then /speckit-specify.",
    ]
    assert created == sorted(e["path"] for e in record["entries"])
    assert "\\" not in done.stdout

    scripts = sorted(p.name for p in (project / ".specify" / "scripts" / "bash").glob("*.sh"))
    assert scripts, "no .sh scripts were installed"
    assert not (project / ".specify" / "scripts" / "powershell").exists()
    skills = sorted(p.parent.name for p in (project / ".claude" / "skills").glob("speckit-*/SKILL.md"))
    assert {"speckit-constitution", "speckit-specify", "speckit-plan"} <= set(skills)
    options = json.loads((project / ".specify" / "init-options.json").read_bytes().decode("utf-8"))
    assert options["speckit_version"] == expected
    assert (project / ".specify" / ".gitattributes").read_bytes() == b"scripts/bash/*.sh text eol=lf\n"

    # The .sh files, and only they, are in the index, as executables.
    staged = [l.split()[1] for l in out if l.startswith("staged ")]
    assert sorted(Path(p).name for p in staged) == scripts
    index = {row.split("\t")[1]: row.split(" ")[0] for row in git_run(project, "ls-files", "-s").splitlines()}
    assert index == {path: "100755" for path in staged}
    assert out[-3] == (
        f"Git: {len(staged)} files were added to the index and nothing was committed. "
        f"{len(created)} paths are uncommitted."
    )
    assert subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=project, capture_output=True).returncode != 0

    before = snap(project, with_mtime=True)
    before_status = status(project)

    again = run_sdd_init(project, env, "init")

    assert again.returncode == 0, again.stderr
    assert again.stdout.splitlines() == [f"Spec Kit {expected} is already initialized. Nothing changed."]
    assert snap(project, with_mtime=True) == before
    assert status(project) == before_status


def test_spec_kit_scripts_run_in_a_clone_made_with_autocrlf(project, env, tmp_path):
    done = run_sdd_init(project, env, "init")
    assert done.returncode == 0, done.stderr
    git(project, env, "add", "-A")
    git(project, env, "commit", "--quiet", "-m", "spec kit")

    clone = tmp_path / "clone"
    git(tmp_path, env, "clone", "--quiet", "-c", "core.autocrlf=true", str(project), str(clone))

    scripts = sorted((clone / ".specify" / "scripts" / "bash").glob("*.sh"))
    assert scripts
    for script in scripts:
        assert b"\r" not in script.read_bytes(), script.name
    # The clone really converts other text files, so the rule is what keeps .sh as LF.
    assert b"\r\n" in (clone / ".specify" / "templates" / "plan-template.md").read_bytes()
    index = {row.split("\t")[1]: row.split(" ")[0] for row in git_run(clone, "ls-files", "-s").splitlines()}
    for script in scripts:
        assert index[script.relative_to(clone).as_posix()] == "100755"
    assert git_run(clone, "status", "--porcelain") == ""

    run_spec_kit_scripts(clone, env)

    # In the converted clone the record still matches: nothing is reported as changed.
    again = run_sdd_init(clone, env, "init")
    assert again.returncode == 0, again.stderr
    assert "is already initialized. Nothing changed." in again.stdout


def test_remove_right_after_init_restores_the_project(project, env):
    (project / "README.md").write_bytes(b"# demo\n")
    git(project, env, "add", "-A")
    git(project, env, "commit", "--quiet", "-m", "first")
    before = snap(project, with_mtime=True)
    before_status = status(project)
    before_index = git_run(project, "ls-files", "-s")

    done = run_sdd_init(project, env, "init")
    assert done.returncode == 0, done.stderr
    assert (project / RECORD).is_file()

    removed = run_sdd_init(project, env, "remove")

    assert removed.returncode == 0, removed.stderr
    out = removed.stdout.splitlines()
    deleted = [l for l in out if l.startswith("deleted ")]
    assert out[-1] == f"Spec Kit removed: {len(deleted)} deleted, 0 kept because they were modified."
    assert snap(project, with_mtime=True) == before
    assert status(project) == before_status
    assert git_run(project, "ls-files", "-s") == before_index
    assert not (project / ".specify").exists() and not (project / ".claude").exists()

