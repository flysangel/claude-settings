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


# ------------------------------------- sdd-init: running the real script

GIT_IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")


def find_bash() -> str:
    """Git Bash on Windows (not the WSL launcher in System32), plain bash elsewhere."""
    import shutil
    import subprocess

    if sys.platform == "win32":
        done = subprocess.run(["git", "--exec-path"], capture_output=True, text=True)
        if done.returncode == 0:
            for parent in Path(done.stdout.strip()).parents:
                candidate = parent / "bin" / "bash.exe"
                if candidate.is_file():
                    return str(candidate)
    return shutil.which("bash") or "bash"


def real_run_env(home: Path) -> dict[str, str]:
    """Environment for running the real script: a temporary home, uv's real cache."""
    import os
    import subprocess

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    for variable, command in (("UV_CACHE_DIR", ["uv", "cache", "dir"]), ("UV_PYTHON_INSTALL_DIR", ["uv", "python", "dir"])):
        if variable not in env:
            env[variable] = subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()
    return env


def run_sdd_init(cwd: Path, env: dict[str, str], command: str):
    """Run the real script the way the skill does: uv run <script> init|remove."""
    import subprocess

    return subprocess.run(
        ["uv", "run", str(SDD_INIT_PY), command],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def run_spec_kit_scripts(project: Path, env: dict[str, str]) -> None:
    """Run the two scripts the speckit-specify and speckit-plan skills call, and check the result."""
    import subprocess

    bash = find_bash()
    for arguments in (
        [".specify/scripts/bash/create-new-feature.sh", "--json", "--short-name", "demo", "Demo"],
        [".specify/scripts/bash/setup-plan.sh", "--json"],
    ):
        done = subprocess.run(
            [bash, *arguments], cwd=project, env=env, capture_output=True, text=True, encoding="utf-8"
        )
        assert done.returncode == 0, f"{arguments[0]} failed ({done.returncode}):\n{done.stdout}\n{done.stderr}"
    assert (project / "specs" / "001-demo" / "plan.md").is_file()


# -------------------------------------------------------------- sdd-update

SDD_UPDATE_PY = REPO_ROOT / "home" / "skills" / "sdd-update" / "scripts" / "sdd_update.py"

OLD_VERSION = "1.0.0"
NEW_VERSION = "1.1.0"

# Files both versions provide with the same content.
_SAME_IN_BOTH: dict[str, str] = {
    ".specify/templates/spec-template.md": "# Spec template\n\nsame in both\n",
    ".specify/scripts/bash/setup-plan.sh": "#!/usr/bin/env bash\necho plan\n",
}

# Files both versions provide with different content, and files only one of them provides.
_BY_VERSION: dict[str, dict[str, str]] = {
    OLD_VERSION: {
        ".claude/skills/speckit-plan/SKILL.md": "---\nname: speckit-plan\nversion: 1.0.0\n---\nplan\n",
        ".claude/skills/speckit-specify/SKILL.md": "---\nname: speckit-specify\nversion: 1.0.0\n---\nspecify\n",
        ".claude/skills/speckit-legacy/SKILL.md": "---\nname: speckit-legacy\nversion: 1.0.0\n---\nlegacy\n",
        ".specify/templates/plan-template.md": "# Plan template\n\nold body\n",
        ".specify/scripts/bash/common.sh": "#!/usr/bin/env bash\necho common 1.0.0\n",
        ".specify/memory/constitution.md": "# Constitution\n\n[PRINCIPLE] old\n",
        ".specify/memory/.constitution-template.json": '{"template": "old"}\n',
    },
    NEW_VERSION: {
        ".claude/skills/speckit-plan/SKILL.md": "---\nname: speckit-plan\nversion: 1.1.0\n---\nplan\n",
        ".claude/skills/speckit-specify/SKILL.md": "---\nname: speckit-specify\nversion: 1.1.0\n---\nspecify\n",
        ".specify/templates/plan-template.md": "# Plan template\n\nnew body\n",
        ".specify/scripts/bash/common.sh": "#!/usr/bin/env bash\necho common 1.1.0\n",
        ".specify/scripts/bash/markdown_sections.py": "print('sections')\n",
        ".specify/scripts/bash/setup-tasks.sh": "#!/usr/bin/env bash\necho tasks\n",
        ".specify/memory/constitution.md": "# Constitution\n\n[PRINCIPLE] new\n",
        ".specify/memory/.constitution-template.json": '{"template": "new"}\n',
    },
}


def versioned_official_files(version: str) -> dict[str, str]:
    """The fake official output of OLD_VERSION or NEW_VERSION (any other version gets the new files)."""
    files = dict(_SAME_IN_BOTH)
    files.update(_BY_VERSION.get(version, _BY_VERSION[NEW_VERSION]))
    files[".specify/init-options.json"] = (
        '{\n  "integration": "claude",\n  "script": "sh",\n  "speckit_version": "%s"\n}\n' % version
    )
    return files


def write_versioned_official_output(dest: Path, version: str) -> None:
    """Write the fake output of version into dest; .sh files are executable, as the official tool makes them."""
    import os

    files = versioned_official_files(version)
    write_tree(dest, files)
    for rel in files:
        if rel.endswith(".sh"):
            os.chmod(dest / rel, 0o755)


def fake_versioned_official(version: str, dest: Path) -> None:
    """A stand-in for running the official tool: writes the fake output of the requested version."""
    write_versioned_official_output(Path(dest), version)


def init_with_version(sdd_init_module, root: Path, version: str = OLD_VERSION, run_official=fake_versioned_official) -> int:
    """Bring Spec Kit <version> into root through sdd-init's own entry point, as if it were the latest release.

    Only the version lookup is replaced; run_official may be the fake above or the real official tool.
    """
    import os

    previous = os.getcwd()
    os.chdir(root)
    try:
        return sdd_init_module.main(["init"], resolve_version=lambda: version, run_official=run_official)
    finally:
        os.chdir(previous)


def _load_sdd_update():
    spec = importlib.util.spec_from_file_location("sdd_update", SDD_UPDATE_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sdd_update"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def sdd_update(sdd_init):
    # sdd_init is requested first so that sdd_update shares that very module (and the tests' patches on it).
    return _load_sdd_update()


def run_sdd_update(cwd: Path, env: dict[str, str], *args: str):
    """Run the real script the way the skill does: uv run <script>."""
    import subprocess

    return subprocess.run(
        ["uv", "run", str(SDD_UPDATE_PY), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
