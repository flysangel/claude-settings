"""Shared fixtures: a temporary home directory and a temporary deploy source."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_PY = REPO_ROOT / "tools" / "deploy.py"

# Newer git versions start maintenance in the background after some commands. It creates and removes
# files such as .git/objects/maintenance.lock while a test is taking a snapshot of the folder, which
# made snapshot tests fail at random. Every git process the tests start, directly or through the
# scripts under test, inherits these settings; they do not touch any configuration file.
_GIT_TEST_CONFIG = {"maintenance.auto": "false", "gc.auto": "0", "gc.autoDetach": "false"}
if "GIT_CONFIG_COUNT" not in os.environ:
    os.environ["GIT_CONFIG_COUNT"] = str(len(_GIT_TEST_CONFIG))
    for _index, (_key, _value) in enumerate(_GIT_TEST_CONFIG.items()):
        os.environ[f"GIT_CONFIG_KEY_{_index}"] = _key
        os.environ[f"GIT_CONFIG_VALUE_{_index}"] = _value


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


# --------------------------------------------------------------- sdd-grill

SDD_GRILL_PY = REPO_ROOT / "home" / "skills" / "sdd-grill" / "scripts" / "sdd_grill.py"

# research.md R4 "Spec Kit 缺少能力": besides the .specify/ folder itself, these files must exist.
SPECKIT_REQUIRED_FILES = [
    ".claude/skills/speckit-constitution/SKILL.md",
    ".claude/skills/speckit-specify/SKILL.md",
    ".specify/scripts/bash/resolve-template.sh",
    ".specify/templates/constitution-template.md",
    ".specify/templates/spec-template.md",
]

CONSTITUTION_TEMPLATE = "# [PROJECT_NAME] Constitution\n\n## Core Principles\n\n### [PRINCIPLE_1_NAME]\n\n[PRINCIPLE_1_DESCRIPTION]\n"
WRITTEN_CONSTITUTION = "# Demo Constitution\n\n## Core Principles\n\n### I. Keep it small\n\n- Every feature MUST be small.\n"

# Spec Kit's own .specify/.gitignore lists feature.json as local state.
SPECKIT_GITIGNORE = "# Local state written by Spec Kit\nfeature.json\n"


def _load_sdd_grill():
    spec = importlib.util.spec_from_file_location("sdd_grill", SDD_GRILL_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sdd_grill"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def sdd_grill():
    return _load_sdd_grill()


def write_fake_speckit(
    root: Path,
    *,
    omit: tuple[str, ...] = (),
    constitution: str | None = None,
    init_options: str | None = None,
    specs: dict[str, str] | None = None,
) -> None:
    """Write a stand-in for a project with Spec Kit: the required files plus optional extras.

    omit leaves out some of SPECKIT_REQUIRED_FILES; constitution is the content of
    .specify/memory/constitution.md (None: no file); specs maps folder names under specs/ to spec.md content.
    """
    files: dict[str, str] = {rel: f"stand-in for {rel}\n" for rel in SPECKIT_REQUIRED_FILES if rel not in omit}
    if ".specify/templates/constitution-template.md" in files:
        files[".specify/templates/constitution-template.md"] = CONSTITUTION_TEMPLATE
    files[".specify/.gitignore"] = SPECKIT_GITIGNORE
    if constitution is not None:
        files[".specify/memory/constitution.md"] = constitution
    if init_options is not None:
        files[".specify/init-options.json"] = init_options
    for name, content in (specs or {}).items():
        files[f"specs/{name}/spec.md"] = content
    write_tree(root, files)
    (root / ".specify").mkdir(exist_ok=True)


def git_commit_all(root: Path, message: str = "commit") -> None:
    git_run(root, "add", "-A")
    git_run(root, "commit", "--quiet", "--allow-empty", "-m", message)


@pytest.fixture
def grill_project(make_project):
    """Factory: a temporary project, optionally a git repository, optionally with a fake Spec Kit."""

    def factory(git: bool = True, speckit: bool = True, **speckit_options) -> Path:
        root = make_project(git=git)
        if speckit:
            write_fake_speckit(root, **speckit_options)
        return root

    return factory


class GrillResult:
    def __init__(self, code: int, stdout: bytes, stderr: bytes):
        import json

        self.code = code
        self.raw = stdout
        self.err = stderr.decode("utf-8")
        self.out = json.loads(stdout.decode("utf-8")) if stdout.strip() else None


def run_grill(module, root: Path, *argv: str, stdin: str | bytes | None = None) -> GrillResult:
    """Call sdd_grill.main the way `uv run sdd_grill.py <argv>` would, with root as the current directory."""
    import io

    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    out, err = io.BytesIO(), io.BytesIO()
    code = module.main(list(argv), root=root, stdin=io.BytesIO(stdin or b""), stdout=out, stderr=err)
    return GrillResult(code, out.getvalue(), err.getvalue())


def run_grill_real(root: Path, env: dict[str, str], *argv: str, stdin: str | None = None):
    """Run the real script through uv in root."""
    import subprocess

    return subprocess.run(
        ["uv", "run", str(SDD_GRILL_PY), *argv],
        cwd=root,
        env=env,
        input=(stdin or "").encode("utf-8"),
        capture_output=True,
    )


# -------------------------------------------------------------- sdd-export

SDD_EXPORT_PY = REPO_ROOT / "home" / "skills" / "sdd-export" / "scripts" / "sdd_export.py"


def _load_sdd_export():
    spec = importlib.util.spec_from_file_location("sdd_export", SDD_EXPORT_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sdd_export"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def sdd_export():
    return _load_sdd_export()


@pytest.fixture
def export_env(tmp_path, monkeypatch):
    """HOME and USERPROFILE point at a temporary folder; global and system git settings are ignored.

    Not autouse for the whole suite (that would change the other features' tests); the sdd-export
    test modules turn it on for every test they hold.
    """
    home = tmp_path / "fake-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    empty = home / "empty-gitconfig"
    empty.write_bytes(b"")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(variable, raising=False)
    return home


def make_old_project(
    parent: Path,
    name: str = "my-tool",
    *,
    git: bool = False,
    constitution: str | None = None,
    specs: dict[str, str] | None = None,
    files: dict[str, str | bytes] | None = None,
) -> Path:
    """A fake old project: optionally a git repository, a constitution, specs/<name>/spec.md and any files."""
    root = parent / name
    root.mkdir(parents=True)
    tree: dict[str, str | bytes] = dict(files or {})
    if constitution is not None:
        tree[".specify/memory/constitution.md"] = constitution
    for folder, content in (specs or {}).items():
        tree[f"specs/{folder}/spec.md"] = content
    write_tree(root, tree)
    if git:
        git_run(root, "init", "--quiet")
        git_run(root, "config", "user.name", "test")
        git_run(root, "config", "user.email", "test@example.invalid")
    return root


def tree_snapshot(root: Path) -> dict[str, tuple]:
    """Relative path -> (type, sha256 of the content, mode); directories and symlinks included."""
    import hashlib
    import os
    import stat as stat_module

    result: dict[str, tuple] = {}
    if not root.exists():
        return result
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs + names):
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat_module.S_ISLNK(info.st_mode):
                result[rel] = ("link", os.readlink(path), None)
            elif stat_module.S_ISDIR(info.st_mode):
                result[rel] = ("dir", None, None)
            else:
                result[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest(), stat_module.S_IMODE(info.st_mode))
    return result


def tree_changes(before: dict[str, tuple], after: dict[str, tuple]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(rel for rel in set(before) & set(after) if before[rel] != after[rel]),
    }


class ExportResult:
    def __init__(self, code: int, stdout: bytes, stderr: bytes):
        import json

        self.code = code
        self.raw = stdout
        self.err = stderr.decode("utf-8")
        self.out = json.loads(stdout.decode("utf-8")) if stdout.strip() else None


def run_export(module, root: Path, *argv: str, stdin: str | bytes | None = None) -> ExportResult:
    """Call sdd_export.main the way `uv run sdd_export.py <argv>` would, with root as the current directory."""
    import io

    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    out, err = io.BytesIO(), io.BytesIO()
    code = module.main(list(argv), root=root, stdin=io.BytesIO(stdin or b""), stdout=out, stderr=err)
    return ExportResult(code, out.getvalue(), err.getvalue())


def run_export_real(root: Path, env: dict[str, str], *argv: str, stdin: str | None = None, script: Path | None = None):
    """Run the real script through uv in root."""
    import subprocess

    return subprocess.run(
        ["uv", "run", str(script or SDD_EXPORT_PY), *argv],
        cwd=root,
        env=env,
        input=(stdin or "").encode("utf-8"),
        capture_output=True,
    )


# ------------------------------------------------------------- sdd-rebuild

SDD_REBUILD_PY = REPO_ROOT / "home" / "skills" / "sdd-rebuild" / "scripts" / "sdd_rebuild.py"
SDD_EXPORT_FIXTURES = REPO_ROOT / "tests" / "unit" / "fixtures" / "sdd_export"
SDD_REBUILD_FIXTURES = REPO_ROOT / "tests" / "unit" / "fixtures" / "sdd_rebuild"


def _load_sdd_rebuild():
    spec = importlib.util.spec_from_file_location("sdd_rebuild", SDD_REBUILD_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sdd_rebuild"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def sdd_rebuild(sdd_export, sdd_grill):
    # sdd_export and sdd_grill are loaded first, so the script shares those very modules (and the tests' patches).
    module = _load_sdd_rebuild()
    # E() and G() read the neighbour cache directly; load it here so no test depends on another test having done so.
    _, _, missing = module.neighbours()
    assert missing == []
    return module


def export_fixture(name: str) -> dict:
    import json

    return json.loads((SDD_EXPORT_FIXTURES / name).read_bytes().decode("utf-8"))


def files_for_draft(draft: dict) -> dict[str, str]:
    """Stand-in files for every evidence path and spec a nutrients draft names (the lineage excepted)."""
    files: dict[str, str] = {}

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence":
                    for entry in item:
                        if entry != "maintainer" and not entry.startswith("commit:") and entry != ".sdd-rebuild/lineage.json":
                            files[entry] = "# stand-in\n"
                elif key == "spec" and isinstance(item, str):
                    files[item] = "# Feature Specification\n"
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(draft)
    return files


def place_export(sdd_export_module, root: Path, nutrients: dict | bytes, readme: bool = True) -> None:
    """Put nutrients into root/.sdd-export/ the way sdd-export's write leaves them (README and .gitattributes too)."""
    import json

    data = json.loads(nutrients.decode("utf-8")) if isinstance(nutrients, bytes) else nutrients
    raw = nutrients if isinstance(nutrients, bytes) else sdd_export_module.serialize(data, "nutrients")
    folder = root / ".sdd-export"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "nutrients.json").write_bytes(raw)
    if readme:
        (folder / "README.md").write_bytes(sdd_export_module.render_readme(data))
    (folder / ".gitattributes").write_bytes(sdd_export_module.GITATTRIBUTES.encode("utf-8"))


def export_with_006(sdd_export_module, root: Path, draft: dict) -> ExportResult:
    """Write a draft into root/.sdd-export/ with sdd-export's real write (check first for the state)."""
    import json

    state = run_export(sdd_export_module, root, "check").out["state"]
    result = run_export(sdd_export_module, root, "write", "--expect", state, stdin=json.dumps(draft, ensure_ascii=False))
    assert result.code == 0, (result.out, result.err)
    return result


def make_rebuild_old(
    sdd_export_module,
    parent: Path,
    draft: dict | None,
    *,
    name: str = "old-tool",
    lineage: dict | bytes | None = None,
    keep_lineage: bool = True,
    git: bool = False,
    extra: dict[str, str | bytes] | None = None,
) -> Path:
    """A fake old project; with a draft, its nutrients are written by sdd-export's real write.

    lineage is the old project's .sdd-rebuild/lineage.json (needed for a draft of generation 2 or more);
    keep_lineage=False removes it after the export, as if someone deleted it.
    """
    files: dict[str, str | bytes] = {"README.md": "# old\n"}
    if draft is not None:
        files.update(files_for_draft(draft))
    if lineage is not None:
        import json

        files[".sdd-rebuild/lineage.json"] = (
            lineage if isinstance(lineage, bytes) else sdd_export_module.serialize(lineage, "lineage")
        )
    files.update(extra or {})
    root = make_old_project(parent, name, git=git, files=files)
    if draft is not None:
        export_with_006(sdd_export_module, root, draft)
    if lineage is not None and not keep_lineage:
        (root / ".sdd-rebuild" / "lineage.json").unlink()
        (root / ".sdd-rebuild").rmdir()
    return root


def make_rebuild_new(
    parent: Path,
    name: str = "new-tool",
    *,
    git: bool = True,
    constitution: str | None = None,
    specs: dict[str, str] | None = None,
    **speckit_options,
) -> Path:
    """A fake new project with Spec Kit set up (the files sdd-grill's speckit_state requires)."""
    root = parent / name
    root.mkdir(parents=True)
    write_fake_speckit(root, constitution=constitution, specs=specs, **speckit_options)
    if git:
        git_run(root, "init", "--quiet")
        git_run(root, "config", "user.name", "test")
        git_run(root, "config", "user.email", "test@example.invalid")
    return root


def simulate_specify(root: Path, short_name: str, content: str | None = None) -> str:
    """What speckit-specify leaves behind: specs/<next number>-<short name>/spec.md and .specify/feature.json."""
    import json
    import re

    numbers = [int(m.group(1)) for p in (root / "specs").glob("*") if (m := re.match(r"^(\d{3,})-", p.name))] \
        if (root / "specs").is_dir() else []
    folder = f"specs/{(max(numbers) + 1 if numbers else 1):03d}-{short_name}"
    write_tree(root, {f"{folder}/spec.md": content or f"# Feature Specification: {short_name}\n"})
    (root / ".specify" / "feature.json").write_bytes(
        (json.dumps({"feature_directory": folder}, indent=2) + "\n").encode("utf-8"))
    return folder


def simulate_constitution(root: Path, content: str | None = None) -> None:
    """What speckit-constitution leaves behind: a filled-in constitution."""
    write_tree(root, {".specify/memory/constitution.md": content or WRITTEN_CONSTITUTION})


class RebuildResult:
    def __init__(self, code: int, stdout: bytes, stderr: bytes):
        import json

        self.code = code
        self.raw = stdout
        self.err = stderr.decode("utf-8")
        self.out = json.loads(stdout.decode("utf-8")) if stdout.strip() else None


def run_rebuild(module, root: Path, *argv: str, stdin: str | bytes | dict | None = None) -> RebuildResult:
    """Call sdd_rebuild.main the way `uv run sdd_rebuild.py <argv>` would, with root as the new project."""
    import io
    import json

    if isinstance(stdin, dict):
        stdin = json.dumps(stdin, ensure_ascii=False)
    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    out, err = io.BytesIO(), io.BytesIO()
    code = module.main(list(argv), root=root, stdin=io.BytesIO(stdin or b""), stdout=out, stderr=err)
    return RebuildResult(code, out.getvalue(), err.getvalue())


def run_rebuild_real(root: Path, env: dict[str, str], *argv: str, stdin: str | None = None, script: Path | None = None):
    """Run the real script through uv in root."""
    import subprocess

    return subprocess.run(
        ["uv", "run", str(script or SDD_REBUILD_PY), *argv],
        cwd=root,
        env=env,
        input=(stdin or "").encode("utf-8"),
        capture_output=True,
    )


def target_item(item: dict, section: str) -> dict:
    """The target entry that keeps a source item as it is (basis "inherit", content null)."""
    if section == "principles":
        return {"id": item["id"], "basis": "inherit", "from": [], "title": None, "text": None}
    if section == "lessons":
        return {"id": item["id"], "basis": "inherit", "from": [], "kind": None, "title": None, "text": None}
    if section == "requirements":
        return {"id": item["id"], "basis": "inherit", "from": [], "kind": None, "text": None}
    return {
        "id": item["id"], "basis": "inherit", "from": [], "title": None, "summary": None,
        "depends_on": list(item["depends_on"]), "existing_spec": None, "spec_dir": None, "reviewed": False,
        "requirements": [target_item(entry, "requirements") for entry in item["requirements"]],
    }


def keep_all_progress(old_project: Path | str, nutrients: dict, old_lineage: str, **overrides) -> dict:
    """A progress (phase deciding, stage items) that keeps every item of the nutrients as it is."""
    progress = {
        "schema": 1,
        "tool": "sdd-rebuild",
        "old_project": str(old_project),
        "language": "zh-TW",
        "phase": "deciding",
        "stage": "items",
        "old_lineage": old_lineage,
        "constitution": {"action": "create", "governance": []},
        "target": {
            "principles": [target_item(p, "principles") for p in nutrients["principles"]],
            "features": [target_item(f, "features") for f in nutrients["features"]],
            "lessons": [target_item(l, "lessons") for l in nutrients["lessons"]],
        },
        "discards": [],
        "pending_decided": [r["id"] for f in nutrients["features"] for r in f["requirements"] if r["status"] == "pending"]
        + [i["id"] for s in ("principles", "lessons") for i in nutrients[s] if i["status"] == "pending"],
        "adjustments": [],
        "deferred": [],
        "for_plan": [],
        "generation": {"constitution": "pending"},
    }
    progress.update(overrides)
    return progress
