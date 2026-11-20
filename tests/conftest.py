"""Shared fixtures: a temporary home directory and a temporary deploy source."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_PY = REPO_ROOT / "tools" / "deploy.py"


def _load_deploy():
    spec = importlib.util.spec_from_file_location("deploy", DEPLOY_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deploy"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def deploy():
    return _load_deploy()


def write_tree(root: Path, files: dict[str, str | bytes]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        path.write_bytes(content)


def snapshot(root: Path, with_mtime: bool = False) -> dict:
    """Map every file and directory under root to its content (and mtime)."""
    result: dict = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            result[rel + "/"] = None
        else:
            data = path.read_bytes()
            result[rel] = (data, path.stat().st_mtime_ns) if with_mtime else data
    return result


DEFAULT_SOURCE = {
    "CLAUDE.md": "# Global preferences\n",
    "skills/sdd-init/SKILL.md": "---\nname: sdd-init\n---\ninit\n",
    "skills/sdd-init/README.md": "sdd-init 簡述\n",
    "skills/sdd-grill/SKILL.md": "---\nname: sdd-grill\n---\ngrill\n",
}


class Env:
    def __init__(self, deploy, tmp_path: Path, capsys):
        self.deploy = deploy
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.source = tmp_path / "repo" / "home"
        self.target = self.home / ".claude"
        self.state = self.target / ".claude-settings"
        self.capsys = capsys
        write_tree(self.source, DEFAULT_SOURCE)

    def run(self, *args: str) -> tuple[int, str]:
        self.capsys.readouterr()
        code = self.deploy.main(list(args), source=self.source, target=self.target)
        captured = self.capsys.readouterr()
        return code, captured.out

    def lines(self, out: str, action: str) -> list[str]:
        return [l for l in out.splitlines() if l.split(" ", 1)[0] == action]


@pytest.fixture
def env(deploy, tmp_path, capsys, monkeypatch):
    e = Env(deploy, tmp_path, capsys)
    monkeypatch.setenv("HOME", str(e.home))
    monkeypatch.setenv("USERPROFILE", str(e.home))
    return e


# ---------------------------------------------------------------- sdd-init

SDD_INIT_PY = REPO_ROOT / "home" / "skills" / "sdd-init" / "scripts" / "sdd_init.py"

FAKE_VERSION = "9.8.7"

# A small stand-in for what the official tool generates. Line endings are LF.
FAKE_OFFICIAL_FILES: dict[str, str] = {
    ".claude/skills/speckit-plan/SKILL.md": "---\nname: speckit-plan\n---\nplan\n",
    ".claude/skills/speckit-specify/SKILL.md": "---\nname: speckit-specify\n---\nspecify\n",
    ".specify/scripts/bash/common.sh": "#!/usr/bin/env bash\necho common\n",
    ".specify/scripts/bash/setup-plan.sh": "#!/usr/bin/env bash\necho plan\n",
    ".specify/templates/plan-template.md": "# Plan template\n\nbody\n",
    ".specify/memory/constitution.md": "# Constitution\n\n[PRINCIPLE]\n",
}


def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs network access and runs the official Spec Kit tool")


def _load_sdd_init():
    spec = importlib.util.spec_from_file_location("sdd_init", SDD_INIT_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sdd_init"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def sdd_init():
    return _load_sdd_init()


def fake_official_files(version: str = FAKE_VERSION) -> dict[str, str]:
    files = dict(FAKE_OFFICIAL_FILES)
    files[".specify/init-options.json"] = (
        '{\n  "integration": "claude",\n  "script": "sh",\n  "speckit_version": "%s"\n}\n' % version
    )
    return files


def write_fake_official_output(dest: Path, version: str = FAKE_VERSION) -> None:
    """Write the fake official output into dest, the way `specify init` would."""
    write_tree(dest, fake_official_files(version))


def git_run(cwd: Path, *args: str) -> str:
    import subprocess

    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)
    return done.stdout.decode("utf-8")


@pytest.fixture
def make_project(tmp_path, monkeypatch):
    """Factory for temporary projects; HOME points at a temporary directory."""
    home = tmp_path / "fake-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    counter = {"n": 0}

    def factory(git: bool = True, name: str | None = None) -> Path:
        counter["n"] += 1
        root = tmp_path / (name or f"project{counter['n']}")
        root.mkdir()
        if git:
            git_run(root, "init", "--quiet")
            git_run(root, "config", "user.name", "test")
            git_run(root, "config", "user.email", "test@example.invalid")
        return root

    return factory
