"""Unit tests for home/skills/sdd-export/scripts/sdd_export.py.

The contracts are specs/006-sdd-export/contracts/cli.md and specs/006-sdd-export/data-model.md.
Every test runs in a fake old project under tmp_path; HOME points at a temporary folder.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    REPO_ROOT,
    SDD_EXPORT_PY,
    git_run,
    make_old_project,
    real_run_env,
    run_export,
    run_export_real,
    tree_changes,
    tree_snapshot,
    write_tree,
)

pytestmark = pytest.mark.usefixtures("export_env")

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sdd_export"
HAS_GIT = shutil.which("git") is not None
needs_git = pytest.mark.skipif(not HAS_GIT, reason="git is not installed")
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0

CONFLICT_ERROR = ".sdd-export/ holds files sdd-export did not create; nothing was read or written"
CHANGED_ERROR = ".sdd-export/ changed since it was checked; check again and confirm the differences before writing"
INVALID_ERROR = "the draft is not valid nutrients"
SECRET_ERROR = "the draft looks like it contains a secret; describe what is needed instead of recording the value"
GITATTRIBUTES = "# Created by sdd-export; keeps these files LF on every platform.\n* text eol=lf\n"


# ------------------------------------------------------------------ helpers


def requirement(rid: str, origin: int = 1, **extra) -> dict:
    item = {
        "id": rid,
        "origin": origin,
        "kind": "functional",
        "text": f"需求 {rid} 的可驗收行為。",
        "revised": [],
        "derived_from": [],
        "source": "code",
        "status": "confirmed",
        "evidence": ["src/app.py"],
    }
    item.update(extra)
    return item


def feature(fid: str, origin: int = 1, requirements: list | None = None, **extra) -> dict:
    item = {
        "id": fid,
        "origin": origin,
        "title": f"功能 {fid}",
        "summary": f"維護者可以使用 {fid}。",
        "revised": [],
        "derived_from": [],
        "source": "code",
        "spec": None,
        "depends_on": [],
        "requirements": requirements if requirements is not None else [requirement(f"{fid}-one", origin)],
    }
    item.update(extra)
    return item


def principle(pid: str, origin: int = 1, **extra) -> dict:
    item = {
        "id": pid,
        "origin": origin,
        "title": f"原則 {pid}",
        "text": "每個功能 MUST 簡單。",
        "revised": [],
        "derived_from": [],
        "source": "doc",
        "status": "confirmed",
        "evidence": ["README.md"],
    }
    item.update(extra)
    return item


def lesson(lid: str, origin: int = 1, kind: str = "decision", **extra) -> dict:
    item = {
        "id": lid,
        "origin": origin,
        "kind": kind,
        "title": f"教訓 {lid}",
        "text": "因為某個理由而這樣決定。",
        "revised": [],
        "derived_from": [],
        "status": "confirmed",
        "evidence": ["README.md"],
    }
    item.update(extra)
    return item


def discarded(did: str, kind: str = "requirement", origin: int = 1, discarded_in: int = 1, **extra) -> dict:
    item = {"id": did, "kind": kind, "origin": origin, "discarded_in": discarded_in, "text": "被捨棄的內容。", "reason": "維護者決定捨棄"}
    item.update(extra)
    return item


def draft(**overrides) -> dict:
    data = {
        "generation": 1,
        "project": "my-tool",
        "language": "zh-Hant",
        "scope": {"coverage": "full", "included": []},
        "principles": [principle("keep-small")],
        "features": [feature("deploy")],
        "lessons": [lesson("atomic-write")],
        "discarded": [],
    }
    data.update(overrides)
    return data


def dump(data) -> str:
    return json.dumps(data, ensure_ascii=False)


BASE_FILES = {"README.md": "# my-tool\n", "src/app.py": "print('hi')\n"}


def project(tmp_path: Path, name: str = "my-tool", **kwargs) -> Path:
    files = dict(BASE_FILES)
    files.update(kwargs.pop("files", {}) or {})
    return make_old_project(tmp_path, name, files=files, **kwargs)


def checks(result) -> list[str]:
    return [error["check"] for error in result.out["errors"]]


def errors_for(result, check: str) -> list[dict]:
    return [error for error in result.out["errors"] if error["check"] == check]


def write_ok(module, root: Path, data: dict, expect: str | None = None):
    if expect is None:
        expect = run_export(module, root, "check").out["state"]
    result = run_export(module, root, "write", "--expect", expect, stdin=dump(data))
    assert result.code == 0, (result.out, result.err)
    return result


@pytest.fixture
def fixed_day(sdd_export, monkeypatch):
    monkeypatch.setattr(sdd_export, "utc_today", lambda: "2026-11-20")
    return "2026-11-20"


# ------------------------------------------------- (1) usage and loading


def test_loading_the_module_does_nothing(sdd_export, tmp_path, monkeypatch):
    import importlib.util

    monkeypatch.chdir(tmp_path)
    before = tree_snapshot(tmp_path)
    spec = importlib.util.spec_from_file_location("sdd_export_again", SDD_EXPORT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert tree_snapshot(tmp_path) == before
    assert callable(module.main)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["nope"],
        ["write"],
        ["write", "--expect"],
        ["check", "extra"],
        ["check", "--scope", "src"],
        ["validate", "--expect", "none"],
        ["files", "--scope"],
        ["check", "--project"],
        ["check", "--unknown"],
    ],
)
def test_usage_errors(sdd_export, tmp_path, argv):
    root = project(tmp_path)
    result = run_export(sdd_export, root, *argv)

    assert result.code == 1
    assert result.out["reason"] == "usage"
    assert result.out["error"]
    assert "usage" in result.err.lower()


def test_exit_codes(sdd_export):
    assert (sdd_export.EXIT_OK, sdd_export.EXIT_FAILED, sdd_export.EXIT_STATE) == (0, 1, 3)


def test_project_option_must_be_a_folder(sdd_export, tmp_path):
    root = project(tmp_path)
    missing = run_export(sdd_export, root, "check", "--project", str(tmp_path / "nowhere"))
    a_file = run_export(sdd_export, root, "check", "--project", str(root / "README.md"))

    for result in (missing, a_file):
        assert result.code == 3
        assert result.out["reason"] == "project"
        assert result.out["error"] in result.err


def test_project_option_points_at_another_folder(sdd_export, tmp_path):
    root = project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = run_export(sdd_export, elsewhere, "check", "--project", str(root))

    assert result.code == 0
    assert result.out["project"] == "my-tool"


def test_main_signature(sdd_export):
    import inspect

    parameters = list(inspect.signature(sdd_export.main).parameters)
    assert parameters == ["argv", "root", "stdin", "stdout", "stderr"]


# ---------------------------------------------------------- (2) output


def test_output_is_one_json_object_in_fixed_form(sdd_export, tmp_path):
    root = project(tmp_path)
    result = run_export(sdd_export, root, "check")

    assert result.raw.endswith(b"}\n")
    assert b"\r" not in result.raw
    assert not result.raw.startswith(b"\xef\xbb\xbf")
    assert result.raw.decode("utf-8") == json.dumps(result.out, ensure_ascii=False, indent=2) + "\n"
    assert result.err == ""


def test_failure_writes_the_error_to_stderr_too(sdd_export, tmp_path):
    root = project(tmp_path)
    result = run_export(sdd_export, root, "validate", stdin="not json")

    assert result.code == 1
    assert result.out["reason"] == "invalid"
    assert result.out["error"] == INVALID_ERROR
    assert INVALID_ERROR in result.err


def test_check_keys_are_in_the_documented_order(sdd_export, tmp_path):
    root = project(tmp_path)
    keys = list(run_export(sdd_export, root, "check").out)

    assert keys[:18] == [
        "project", "git", "writable", "export_dir", "nutrients", "view", "view_secret_lines", "gitattributes", "state",
        "lineage", "generation", "existing_generation", "constitution", "specs", "lineage_missing_specs", "inventory",
        "existing", "lineage_content",
    ]


# ------------------------------------------------------ (3) serialization


def test_serialization_rules(sdd_export):
    data = dict(reversed(list({**draft(), "tool": "sdd-export", "schema": 1, "exported_at": "2026-11-20"}.items())))
    raw = sdd_export.serialize(data, "nutrients")

    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert raw.endswith(b"}\n") and not raw.endswith(b"\n\n")
    text = raw.decode("utf-8")
    assert "功能 deploy" in text  # not escaped
    assert '\n  "tool": "sdd-export",\n' in text  # two-space indent
    keys = list(json.loads(text))
    assert keys == ["tool", "schema", "generation", "project", "exported_at", "language", "scope",
                    "principles", "features", "lessons", "discarded"]


def test_serialization_orders_nested_keys(sdd_export):
    item = feature("deploy")
    shuffled = dict(reversed(list(item.items())))
    shuffled["requirements"] = [dict(reversed(list(requirement("r1").items())))]
    data = {**draft(features=[shuffled]), "tool": "sdd-export", "schema": 1, "exported_at": "2026-11-20"}
    parsed = json.loads(sdd_export.serialize(data, "nutrients"))

    assert list(parsed["features"][0]) == ["id", "origin", "title", "summary", "revised", "derived_from", "source",
                                           "spec", "depends_on", "requirements"]
    assert list(parsed["features"][0]["requirements"][0]) == ["id", "origin", "kind", "text", "revised",
                                                               "derived_from", "source", "status", "evidence"]
    assert list(parsed["principles"][0]) == ["id", "origin", "title", "text", "revised", "derived_from", "source",
                                             "status", "evidence"]
    assert list(parsed["lessons"][0]) == ["id", "origin", "kind", "title", "text", "revised", "derived_from",
                                          "status", "evidence"]
    assert list(parsed["scope"]) == ["coverage", "included"]


def test_serialization_keeps_array_order(sdd_export):
    data = {**draft(features=[feature("b"), feature("a")]), "tool": "sdd-export", "schema": 1, "exported_at": "x"}
    parsed = json.loads(sdd_export.serialize(data, "nutrients"))

    assert [f["id"] for f in parsed["features"]] == ["b", "a"]


def test_serialization_of_a_lineage(sdd_export):
    data = lineage_record()
    parsed = json.loads(sdd_export.serialize(dict(reversed(list(data.items()))), "lineage"))

    assert list(parsed) == ["tool", "schema", "generation", "rebuilt_at", "source", "principles", "features",
                            "lessons", "discarded"]
    assert list(parsed["source"]) == ["project", "generation", "nutrients_schema"]
    assert list(parsed["features"][0]) == ["id", "origin", "title", "summary", "revised", "derived_from", "source",
                                           "spec_dir", "spec", "depends_on", "requirements"]


# --------------------------------------------------------------- (4) hash


def test_content_hash_ignores_line_endings(sdd_export):
    lf = sdd_export.content_hash(b"a\nb\n")

    assert sdd_export.content_hash(b"a\r\nb\r\n") == lf
    assert sdd_export.content_hash(b"a\rb\r") == lf
    assert sdd_export.content_hash(b"a\nc\n") != lf
    assert lf == hashlib.sha256(b"a\nb\n").hexdigest()


# --------------------------------------------------------------- (5) path


@pytest.mark.parametrize("path", ["src/app.py", "a", "specs/001-x/spec.md", ".sdd-rebuild/lineage.json"])
def test_relative_paths_are_accepted(sdd_export, path):
    assert sdd_export.path_problem(path) is None


@pytest.mark.parametrize(
    "path",
    ["", "/etc/passwd", "./src/app.py", "src/../x", "..", "C:/x", "c:x", "src\\app.py", "src//app.py", "src/"],
)
def test_bad_paths_are_rejected(sdd_export, path):
    assert sdd_export.path_problem(path) is not None


# ----------------------------------------------------------------- (6) id


@pytest.mark.parametrize("value", ["a", "deploy", "deploy-no-overwrite", "a1-b2", "x" * 64])
def test_good_ids(sdd_export, value):
    assert sdd_export.valid_id(value)


@pytest.mark.parametrize("value", ["", "Deploy", "a_b", "-a", "a-", "a--b", "a b", "x" * 65, 3, None])
def test_bad_ids(sdd_export, value):
    assert not sdd_export.valid_id(value)


# ------------------------------------------------------------- (7) schema


def test_newer_schema_is_recognised(sdd_export):
    assert sdd_export.SCHEMA == 1
    assert sdd_export.schema_is_newer(2)
    assert not sdd_export.schema_is_newer(1)


# ----------------------------------------------------------- (8) secrets

SECRET_SAMPLES = [
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
    "token ghp_" + "a" * 24,
    "github_pat_" + "A1_" * 8,
    "key sk-" + "b" * 24,
    "xoxb-" + "1234567890ab",
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "https://alice:s3cr3tvalue@example.invalid/x",
    "password=hunter2",
    "PASSWORD: hunter2",
    "secret = abc123",
    "token: xyz",
    "api_key=abc",
    "API-KEY: abc",
    "apikey=abc",
]


@pytest.mark.parametrize("sample", SECRET_SAMPLES)
def test_secret_patterns_are_found(sdd_export, sample):
    assert sdd_export.secret_lines("first line\n" + sample + "\n") == [2]


@pytest.mark.parametrize(
    "sample",
    [
        "a perfectly ordinary sentence",
        "the_password_field_is_required",
        "configure the api key in settings",
        "token",
        "sk-short",
        "averyveryveryverylongidentifierwithoutanythingsecret_1234567890",
        "使用者輸入密碼後登入。",
    ],
)
def test_ordinary_text_is_not_a_secret(sdd_export, sample):
    assert sdd_export.secret_lines(sample) == []


def test_file_scan_gives_line_numbers_only(sdd_export, tmp_path):
    path = tmp_path / "settings.py"
    path.write_bytes(b"a = 1\r\npassword = \"hunter2\"\r\nb = 2\n")

    hits = sdd_export.scan_file(path)

    assert hits == [2]


SECRET_FILE_NAMES = [
    ".env", ".env.local", ".env.example", "key.pem", "server.key", "cert.p12", "cert.pfx", "store.jks",
    "app.keystore", "db.kdbx", "id_rsa", "id_rsa.pub", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", "_netrc",
    ".npmrc", ".pypirc", "prod.tfvars", "terraform.tfstate", "terraform.tfstate.backup", "credentials",
    "credentials.json", "secrets.yaml", "my-secret.json", "app-secrets.yaml", "x-secret.yml",
    "service-account-prod.json", ".ENV", "Key.PEM",
]


@pytest.mark.parametrize("name", SECRET_FILE_NAMES)
def test_secret_file_names(sdd_export, name):
    assert sdd_export.is_secret_path(name)
    assert sdd_export.is_secret_path(f"config/{name}")


@pytest.mark.parametrize("folder", [".ssh", ".aws", ".gnupg", ".SSH"])
def test_everything_under_secret_folders(sdd_export, folder):
    assert sdd_export.is_secret_path(f"{folder}/config")
    assert sdd_export.is_secret_path(f"home/{folder}/known_hosts")


@pytest.mark.parametrize("name", ["src/app.py", "environment.md", "keys.md", "docs/secret-santa.md", "README.md",
                                  "credentials_test.py", "envs/x.py", "secret.txt"])
def test_ordinary_file_names(sdd_export, name):
    assert not sdd_export.is_secret_path(name)


# ---------------------------------------------------------------- (10) git


def record_git_calls(sdd_export, monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []
    real = subprocess.run

    def spy(args, *rest, **kwargs):
        if isinstance(args, (list, tuple)) and args and args[0] == "git":
            calls.append(list(args))
        return real(args, *rest, **kwargs)

    monkeypatch.setattr(sdd_export.subprocess, "run", spy)
    return calls


@needs_git
def test_git_is_only_used_read_only_with_no_optional_locks(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path, git=True)
    git_run(root, "add", "-A")
    git_run(root, "commit", "--quiet", "-m", "first")
    head = git_run(root, "rev-parse", "HEAD").strip()
    calls = record_git_calls(sdd_export, monkeypatch)

    run_export(sdd_export, root, "check")
    run_export(sdd_export, root, "files")
    data = draft(lessons=[lesson("atomic-write", evidence=[f"commit:{head[:7]}"])])
    run_export(sdd_export, root, "validate", stdin=dump(data))
    run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(data))

    assert calls
    for call in calls:
        assert call[1] == "--no-optional-locks", call
        assert call[2] in ("rev-parse", "ls-files", "cat-file"), call
        if call[2] == "cat-file":
            assert call[3] == "-e"


@pytest.mark.skipif(sys.platform == "win32", reason="a shell script named git is not found by Windows")
def test_fake_git_first_on_path_records_only_read_only_calls(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    log = tmp_path / "git-calls.log"
    fake = bin_dir / "git"
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 1\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    for command in ("check", "files"):
        assert run_export(sdd_export, root, command).code == 0
    run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(draft()))

    lines = log.read_text().splitlines()
    assert lines
    for line in lines:
        words = line.split()
        assert words[0] == "--no-optional-locks", line
        assert words[1] in ("rev-parse", "ls-files", "cat-file"), line


def test_without_git_everything_still_works(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "no-such-bin"))

    check = run_export(sdd_export, root, "check")
    files = run_export(sdd_export, root, "files")
    bad_commit = draft(lessons=[lesson("atomic-write", evidence=["commit:abcdef1"])])
    validate = run_export(sdd_export, root, "validate", stdin=dump(bad_commit))

    assert check.code == 0 and check.out["git"] is False
    assert files.code == 0 and [f["path"] for f in files.out["files"]] == ["README.md", "src/app.py"]
    assert validate.code == 1 and "evidence" in checks(validate)


def test_not_a_git_repository(sdd_export, tmp_path):
    root = project(tmp_path)

    assert run_export(sdd_export, root, "check").out["git"] is False


@needs_git
def test_a_git_repository(sdd_export, tmp_path):
    root = project(tmp_path, git=True)

    assert run_export(sdd_export, root, "check").out["git"] is True


# ---------------------------------------------------------------- lineage


def lineage_record(**overrides) -> dict:
    data = {
        "tool": "sdd-rebuild",
        "schema": 1,
        "generation": 2,
        "rebuilt_at": "2026-11-20",
        "source": {"project": "my-tool", "generation": 1, "nutrients_schema": 1},
        "principles": [],
        "features": [
            {
                "id": "deploy",
                "origin": 1,
                "title": "功能 deploy",
                "summary": "維護者可以使用 deploy。",
                "revised": [],
                "derived_from": [],
                "source": "spec",
                "spec_dir": "specs/001-deploy",
                "spec": "specs/001-deploy/spec.md",
                "depends_on": [],
                "requirements": [
                    {
                        "id": "deploy-one",
                        "origin": 1,
                        "kind": "functional",
                        "text": "需求 deploy-one 的可驗收行為。",
                        "revised": [],
                        "derived_from": [],
                        "source": "spec",
                    }
                ],
            }
        ],
        "lessons": [
            {
                "id": "atomic-write",
                "origin": 1,
                "kind": "pitfall",
                "title": "教訓 atomic-write",
                "text": "因為某個理由而這樣決定。",
                "revised": [],
                "derived_from": [],
            }
        ],
        "discarded": [discarded("deploy-symlink", discarded_in=2)],
    }
    data.update(overrides)
    return data


# ================================================================== check

SPEC_TEXT = "# Feature Specification\n\n需求。\n"
THREE_SPECS = {"002-status": SPEC_TEXT, "001-deploy": SPEC_TEXT, "003-remove": SPEC_TEXT}


def spec_project(tmp_path: Path, **kwargs) -> Path:
    return project(tmp_path, constitution="# Constitution\n\n原則。\n", specs=THREE_SPECS, **kwargs)


def spec_draft() -> dict:
    features = [
        feature("deploy", source="spec", spec="specs/001-deploy/spec.md",
                requirements=[requirement("deploy-one", source="spec", evidence=["specs/001-deploy/spec.md"])]),
        feature("status", source="spec", spec="specs/002-status/spec.md", depends_on=["deploy"],
                requirements=[requirement("status-one", source="spec", evidence=["specs/002-status/spec.md"])]),
        feature("remove", source="spec", spec="specs/003-remove/spec.md", depends_on=["deploy"],
                requirements=[requirement("remove-one", source="spec", evidence=["specs/003-remove/spec.md"])]),
    ]
    principles = [principle("keep-small", source="constitution", evidence=[".specify/memory/constitution.md"])]
    return draft(principles=principles, features=features)


def test_check_without_spec_kit_or_git(sdd_export, tmp_path):
    root = project(tmp_path)
    result = run_export(sdd_export, root, "check")

    assert result.code == 0
    out = result.out
    assert out["project"] == "my-tool"
    assert out["git"] is False
    assert out["writable"] is True
    assert (out["export_dir"], out["nutrients"], out["view"], out["gitattributes"]) == ("none", "none", "none", "missing")
    assert out["state"] == "none"
    assert (out["lineage"], out["generation"], out["existing_generation"]) == ("none", 1, None)
    assert out["constitution"] is None
    assert out["specs"] == [] and out["lineage_missing_specs"] == []
    assert out["existing"] is None and out["lineage_content"] is None
    assert "error" not in out and "reason" not in out


def test_check_lists_constitution_and_specs_by_name(sdd_export, tmp_path):
    root = spec_project(tmp_path)
    out = run_export(sdd_export, root, "check").out

    assert out["constitution"] == ".specify/memory/constitution.md"
    assert out["specs"] == [
        {"dir": "specs/001-deploy", "spec": "specs/001-deploy/spec.md", "in_lineage": False},
        {"dir": "specs/002-status", "spec": "specs/002-status/spec.md", "in_lineage": False},
        {"dir": "specs/003-remove", "spec": "specs/003-remove/spec.md", "in_lineage": False},
    ]


def test_check_ignores_spec_folders_without_spec_md(sdd_export, tmp_path):
    root = project(tmp_path, files={"specs/004-x/plan.md": "plan\n", "specs/notes.md": "x\n"})

    assert run_export(sdd_export, root, "check").out["specs"] == []


def test_export_dir_empty(sdd_export, tmp_path):
    root = project(tmp_path)
    (root / ".sdd-export").mkdir()
    out = run_export(sdd_export, root, "check").out

    assert out["export_dir"] == "empty"
    assert out["state"] == "none"


def test_export_dir_ours_after_write(sdd_export, tmp_path, fixed_day):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    result = run_export(sdd_export, root, "check")

    assert result.code == 0
    out = result.out
    assert (out["export_dir"], out["nutrients"], out["view"], out["gitattributes"]) == ("ours", "unchanged", "current", "ok")
    assert out["existing"]["tool"] == "sdd-export"
    assert out["existing"]["features"][0]["id"] == "deploy"
    assert out["existing_generation"] == 1
    assert len(out["state"]) == 64


def test_export_dir_ours_without_readme_and_gitattributes(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    (root / ".sdd-export" / "README.md").unlink()
    (root / ".sdd-export" / ".gitattributes").unlink()
    out = run_export(sdd_export, root, "check").out

    assert out["export_dir"] == "ours"
    assert (out["nutrients"], out["view"], out["gitattributes"]) == ("unknown", "missing", "missing")


def make_conflict(root: Path, how: str) -> None:
    folder = root / ".sdd-export"
    if how == "file":
        folder.write_text("not a folder\n")
        return
    folder.mkdir(exist_ok=True)
    if how == "extra-file":
        (folder / "notes.txt").write_text("mine\n")
    elif how == "readme-only":
        (folder / "README.md").write_text("# my own notes\n")
    elif how == "other-tool":
        (folder / "nutrients.json").write_text('{"tool": "someone-else", "schema": 1}\n')
    elif how == "subfolder":
        (folder / "nutrients.json").mkdir()


@pytest.mark.parametrize("how", ["file", "extra-file", "readme-only", "other-tool", "subfolder"])
def test_export_dir_conflict(sdd_export, tmp_path, how):
    root = project(tmp_path)
    make_conflict(root, how)
    before = tree_snapshot(root)
    result = run_export(sdd_export, root, "check")

    assert result.code == 3
    out = result.out
    assert out["export_dir"] == "conflict"
    assert out["reason"] == "conflict"
    assert out["error"] == CONFLICT_ERROR
    assert CONFLICT_ERROR in result.err
    assert out["conflicts"]
    assert out["project"] == "my-tool"
    for key in ("nutrients", "view", "view_secret_lines", "state", "lineage", "generation", "inventory", "existing",
                "specs"):
        assert out[key] is None, key
    assert tree_snapshot(root) == before


def test_conflict_lists_what_is_not_ours(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    (root / ".sdd-export" / "notes.txt").write_text("mine\n")
    (root / ".sdd-export" / "old").mkdir()

    out = run_export(sdd_export, root, "check").out

    assert out["conflicts"] == [".sdd-export/notes.txt", ".sdd-export/old"]


def test_conflict_when_the_path_is_a_file(sdd_export, tmp_path):
    root = project(tmp_path)
    (root / ".sdd-export").write_text("x\n")

    assert run_export(sdd_export, root, "check").out["conflicts"] == [".sdd-export"]


def test_export_dir_unreadable(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    (root / ".sdd-export" / "nutrients.json").write_bytes(b"\xff\xfe not utf-8")
    result = run_export(sdd_export, root, "check")

    assert result.code == 3
    assert (result.out["export_dir"], result.out["reason"]) == ("unreadable", "nutrients-unreadable")
    assert result.out["existing"] is None


@pytest.mark.parametrize("content", [b"[1, 2]\n", b"\xef\xbb\xbf{}\n", b"{not json\n"])
def test_export_dir_unreadable_variants(sdd_export, tmp_path, content):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    (root / ".sdd-export" / "nutrients.json").write_bytes(content)

    assert run_export(sdd_export, root, "check").out["reason"] == "nutrients-unreadable"


def test_export_dir_newer(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    path = root / ".sdd-export" / "nutrients.json"
    data = json.loads(path.read_text("utf-8"))
    data["schema"] = 2
    data["something_new"] = True
    path.write_text(json.dumps(data), "utf-8")
    result = run_export(sdd_export, root, "check")

    assert result.code == 3
    assert (result.out["export_dir"], result.out["reason"]) == ("newer", "nutrients-newer")


def test_export_dir_invalid_lists_field_paths(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    path = root / ".sdd-export" / "nutrients.json"
    data = json.loads(path.read_text("utf-8"))
    data["features"][0]["requirements"][0]["kind"] = "wish"
    data["plan"] = "copied plan"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    result = run_export(sdd_export, root, "check")

    assert result.code == 3
    assert (result.out["export_dir"], result.out["reason"]) == ("invalid", "nutrients-invalid")
    paths = [error["path"] for error in result.out["errors"]]
    assert "features[0].requirements[0].kind" in paths
    assert "plan" in paths
    assert result.out["existing"] is None


def test_existing_nutrients_are_not_checked_against_the_files(sdd_export, tmp_path):
    """Evidence that later disappears does not make the exported nutrients invalid."""
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    (root / "src" / "app.py").unlink()

    assert run_export(sdd_export, root, "check").out["export_dir"] == "ours"


def edit_nutrients(root: Path, change) -> None:
    path = root / ".sdd-export" / "nutrients.json"
    data = json.loads(path.read_text("utf-8"))
    change(data)
    path.write_bytes(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")


def test_nutrients_and_view_values(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    readme = root / ".sdd-export" / "README.md"

    edit_nutrients(root, lambda d: d["features"][0]["requirements"][0].update(text="改過的文字。"))
    out = run_export(sdd_export, root, "check").out
    assert (out["nutrients"], out["view"]) == ("edited", "stale")

    content = readme.read_text("utf-8")
    readme.write_text(content + "\nmy own line\n", "utf-8")
    out = run_export(sdd_export, root, "check").out
    assert (out["nutrients"], out["view"]) == ("edited", "edited")

    readme.write_text("no marker\n" + content.split("\n", 1)[1], "utf-8")
    out = run_export(sdd_export, root, "check").out
    assert (out["nutrients"], out["view"]) == ("unknown", "edited")

    readme.unlink()
    out = run_export(sdd_export, root, "check").out
    assert (out["nutrients"], out["view"]) == ("unknown", "missing")


def test_gitattributes_values(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    attributes = root / ".sdd-export" / ".gitattributes"
    assert run_export(sdd_export, root, "check").out["gitattributes"] == "ok"

    attributes.write_text("* text eol=lf\n*.md diff\n")
    assert run_export(sdd_export, root, "check").out["gitattributes"] == "edited"

    attributes.unlink()
    assert run_export(sdd_export, root, "check").out["gitattributes"] == "missing"


def test_state_follows_the_content(sdd_export, tmp_path):
    root = project(tmp_path)
    assert run_export(sdd_export, root, "check").out["state"] == "none"
    write_ok(sdd_export, root, draft())
    first = run_export(sdd_export, root, "check").out["state"]

    edit_nutrients(root, lambda d: d.update(project="other"))
    second = run_export(sdd_export, root, "check").out["state"]
    assert second != first

    for name in ("nutrients.json", "README.md"):
        path = root / ".sdd-export" / name
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert run_export(sdd_export, root, "check").out["state"] == second

    (root / ".sdd-export" / "README.md").unlink()
    assert run_export(sdd_export, root, "check").out["state"] not in (second, "none")


@pytest.mark.skipif(sys.platform == "win32" or IS_ROOT, reason="needs POSIX permissions and a non-root user")
def test_writable_false_in_a_read_only_project(sdd_export, tmp_path):
    root = project(tmp_path)
    root.chmod(0o555)
    try:
        out = run_export(sdd_export, root, "check").out
    finally:
        root.chmod(0o755)

    assert out["writable"] is False


def test_writable_uses_os_access(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.setattr(sdd_export.os, "access", lambda path, mode: False)

    assert run_export(sdd_export, root, "check").out["writable"] is False


def test_writable_looks_at_the_existing_export_folder(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    (root / ".sdd-export").mkdir()
    seen = []
    monkeypatch.setattr(sdd_export.os, "access", lambda path, mode: seen.append(Path(path)) or True)

    run_export(sdd_export, root, "check")

    assert root / ".sdd-export" in [p if p.is_absolute() else root / p for p in seen]


def test_check_reads_only(sdd_export, tmp_path):
    root = spec_project(tmp_path, files={"pyproject.toml": "[project]\nname='x'\ndependencies=['requests']\n"})
    before = tree_snapshot(root)
    parent_before = sorted(p.name for p in tmp_path.iterdir())

    for _ in range(2):
        assert run_export(sdd_export, root, "check").code == 0

    assert tree_snapshot(root) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == parent_before
    for name in (".venv", "uv.lock", ".sdd-export"):
        assert not (root / name).exists()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_check_through_uv_matches_main(sdd_export, tmp_path, export_env):
    root = spec_project(tmp_path, files={"pyproject.toml": "[project]\nname='x'\ndependencies=['requests']\n"})
    script_copy = tmp_path / "skill-copy" / "sdd_export.py"
    script_copy.parent.mkdir()
    script_copy.write_bytes(SDD_EXPORT_PY.read_bytes())
    before = tree_snapshot(root)

    done = run_export_real(root, real_run_env(export_env), "check", script=script_copy)
    direct = run_export(sdd_export, root, "check")

    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert json.loads(done.stdout.decode("utf-8")) == direct.out
    assert tree_snapshot(root) == before


# =============================================================== validate


def validate(module, root: Path, data) -> object:
    return run_export(module, root, "validate", stdin=data if isinstance(data, (str, bytes)) else dump(data))


def test_valid_draft(sdd_export, tmp_path):
    root = project(tmp_path)
    result = validate(sdd_export, root, draft())

    assert result.code == 0, result.out
    assert result.out["ok"] is True
    assert result.out["errors"] == []
    assert "error" not in result.out
    assert list(result.out) == ["ok", "errors", "counts", "diff"]


@pytest.mark.parametrize("stdin", [b"", b"not json", b"[1]", b"\xff\xfe", b"\xef\xbb\xbf{}"])
def test_json_check(sdd_export, tmp_path, stdin):
    root = project(tmp_path)
    result = validate(sdd_export, root, stdin)

    assert result.code == 1
    assert checks(result) == ["json"]
    assert result.out["diff"] is None


def test_missing_and_extra_keys(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft()
    del data["lessons"]
    data["plan"] = "the plan"
    data["features"][0]["tasks"] = ["t1"]
    data["features"][0]["requirements"][0]["code"] = "x = 1"
    result = validate(sdd_export, root, data)

    assert result.code == 1
    assert result.out["reason"] == "invalid"
    assert result.out["error"] == INVALID_ERROR
    paths = {error["path"] for error in errors_for(result, "field")}
    assert {"lessons", "plan", "features[0].tasks", "features[0].requirements[0].code"} <= paths
    assert result.out["diff"] is None


@pytest.mark.parametrize("key", ["tool", "schema", "exported_at"])
def test_script_fields_are_refused_in_a_draft(sdd_export, tmp_path, key):
    root = project(tmp_path)
    data = draft()
    data[key] = {"tool": "sdd-export", "schema": 1, "exported_at": "2026-11-20"}[key]

    result = validate(sdd_export, root, data)

    assert [e["path"] for e in errors_for(result, "field")] == [key]


@pytest.mark.parametrize(
    "change, path",
    [
        (lambda d: d.update(language="en"), "language"),
        (lambda d: d.update(generation=0), "generation"),
        (lambda d: d.update(generation="1"), "generation"),
        (lambda d: d.update(generation=True), "generation"),
        (lambda d: d.update(project=""), "project"),
        (lambda d: d.update(project="my/tool"), "project"),
        (lambda d: d.update(project="my\\tool"), "project"),
        (lambda d: d["scope"].update(coverage="most"), "scope.coverage"),
        (lambda d: d["features"][0].update(source="guess"), "features[0].source"),
        (lambda d: d["features"][0]["requirements"][0].update(kind="wish"), "features[0].requirements[0].kind"),
        (lambda d: d["features"][0]["requirements"][0].update(source="spec-ish"), "features[0].requirements[0].source"),
        (lambda d: d["features"][0]["requirements"][0].update(status="maybe"), "features[0].requirements[0].status"),
        (lambda d: d["principles"][0].update(source="code-ish"), "principles[0].source"),
        (lambda d: d["lessons"][0].update(kind="tip"), "lessons[0].kind"),
        (lambda d: d["lessons"][0].update(title=""), "lessons[0].title"),
        (lambda d: d["lessons"][0].update(evidence="README.md"), "lessons[0].evidence"),
        (lambda d: d["features"][0].update(requirements=[]), "features[0].requirements"),
        (lambda d: d.update(features=[]), "features"),
        (lambda d: d.update(discarded=[discarded("old", kind="idea")]), "discarded[0].kind"),
        (lambda d: d.update(discarded=[discarded("old", reason="")]), "discarded[0].reason"),
        (lambda d: d["features"][0].update(revised="2"), "features[0].revised"),
        (lambda d: d["features"][0].update(spec=3), "features[0].spec"),
    ],
)
def test_field_check(sdd_export, tmp_path, change, path):
    root = project(tmp_path)
    data = draft()
    change(data)
    result = validate(sdd_export, root, data)

    assert result.code == 1
    assert path in [e["path"] for e in errors_for(result, "field")], result.out["errors"]


@pytest.mark.parametrize("kind", ["principle", "feature", "requirement", "lesson", "doubt"])
def test_discarded_kinds(sdd_export, tmp_path, kind):
    root = project(tmp_path)

    assert validate(sdd_export, root, draft(discarded=[discarded("old-thing", kind=kind)])).code == 0


@pytest.mark.parametrize("kind", ["story", "functional", "edge-case", "success-criterion", "assumption"])
def test_requirement_kinds(sdd_export, tmp_path, kind):
    root = project(tmp_path)
    data = draft()
    data["features"][0]["requirements"][0]["kind"] = kind

    assert validate(sdd_export, root, data).code == 0


def test_empty_sections_are_allowed(sdd_export, tmp_path):
    root = project(tmp_path)

    assert validate(sdd_export, root, draft(principles=[], lessons=[], discarded=[])).code == 0


def test_id_check(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(
        principles=[principle("Bad_Id")],
        features=[feature("deploy"), feature("deploy", requirements=[requirement("deploy-two")])],
    )
    result = validate(sdd_export, root, data)

    paths = [e["path"] for e in errors_for(result, "id")]
    assert "principles[0].id" in paths
    assert "features[1].id" in paths


def test_ids_are_unique_across_sections(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(lessons=[lesson("deploy")])

    assert "lessons[0].id" in [e["path"] for e in errors_for(validate(sdd_export, root, data), "id")]


@pytest.mark.parametrize(
    "change, path",
    [
        (lambda d: d["principles"][0].update(origin=2), "principles[0].origin"),
        (lambda d: d["principles"][0].update(origin=0), "principles[0].origin"),
        (lambda d: d["principles"][0].update(revised=[1]), "principles[0].revised"),
        (lambda d: d["principles"][0].update(origin=1, revised=[3]), "principles[0].revised"),
        (lambda d: d["lessons"][0].update(revised=[2, 2]), "lessons[0].revised"),
        (lambda d: d.update(discarded=[discarded("x", origin=1, discarded_in=2)]), "discarded[0].discarded_in"),
    ],
)
def test_range_check(sdd_export, tmp_path, change, path):
    root = project(tmp_path)
    data = draft()
    change(data)

    assert path in [e["path"] for e in errors_for(validate(sdd_export, root, data), "range")]


def test_revised_strictly_increasing_is_accepted(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(generation=1)
    data["principles"][0]["revised"] = []

    assert validate(sdd_export, root, data).code == 0


@pytest.mark.parametrize("block", ["```", "```python", "~~~", "  ````", "~~~~ text"])
def test_code_blocks_are_refused(sdd_export, tmp_path, block):
    root = project(tmp_path)
    data = draft()
    data["features"][0]["requirements"][0]["text"] = f"說明\n{block}\nx = 1\n"

    result = validate(sdd_export, root, data)

    assert [e["path"] for e in errors_for(result, "code-block")] == ["features[0].requirements[0].text"]


def test_inline_backticks_are_fine(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft()
    data["features"][0]["requirements"][0]["text"] = "執行 `uv run` 之後顯示結果；``雙反引號``也可以。"

    assert validate(sdd_export, root, data).code == 0


def test_secret_in_a_string(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft()
    data["features"][0]["requirements"][0]["text"] = "以 password=abc123 登入"
    result = validate(sdd_export, root, data)

    assert result.code == 1
    assert result.out["reason"] == "secret"
    assert result.out["error"] == SECRET_ERROR
    assert [e["path"] for e in errors_for(result, "secret")] == ["features[0].requirements[0].text"]
    assert "abc123" not in result.raw.decode("utf-8")
    assert "abc123" not in result.err


def test_secret_wins_over_other_errors(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(language="en")
    data["lessons"][0]["text"] = "token: zzz-value"
    result = validate(sdd_export, root, data)

    assert result.out["reason"] == "secret"
    assert {"secret", "field"} <= set(checks(result))
    assert "zzz-value" not in result.raw.decode("utf-8")


def test_details_never_repeat_a_secret(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft()
    data["features"][0]["requirements"][0]["evidence"] = ["password=abc123"]
    data["features"][0]["source"] = "password=abc123"
    result = validate(sdd_export, root, data)

    assert "abc123" not in result.raw.decode("utf-8")


@pytest.mark.parametrize(
    "evidence",
    ["src/app.py", "src", "README.md", "maintainer", ".specify/memory/constitution.md"],
)
def test_good_evidence(sdd_export, tmp_path, evidence):
    """.sdd-rebuild/lineage.json as evidence is covered by test_gen2_draft_follows_the_lineage."""
    root = project(tmp_path, files={".specify/memory/constitution.md": "c\n"})
    data = draft()
    data["lessons"][0]["evidence"] = [evidence]

    assert validate(sdd_export, root, data).code == 0


@pytest.mark.parametrize(
    "evidence",
    ["src/missing.py", "/etc/passwd", "../outside.txt", "src/../README.md", "commit:abcdef1", "commit:ABCDEF1",
     "commit:abc", "C:/x", ".specify/templates/x.md", "maintainers", ""],
)
def test_bad_evidence(sdd_export, tmp_path, evidence):
    root = project(tmp_path, files={".specify/templates/x.md": "t\n", "../outside.txt": "x\n"})
    data = draft()
    data["lessons"][0]["evidence"] = [evidence]
    result = validate(sdd_export, root, data)

    assert result.code == 1
    assert [e["path"] for e in result.out["errors"]] == ["lessons[0].evidence[0]"]
    assert set(checks(result)) <= {"evidence", "field"}


def test_evidence_to_a_secret_file_is_refused_as_a_secret(sdd_export, tmp_path):
    root = project(tmp_path, files={".env": "API_KEY=dummy\n"})
    data = draft()
    data["lessons"][0]["evidence"] = [".env"]
    result = validate(sdd_export, root, data)

    assert result.code == 1
    assert result.out["reason"] == "secret"
    assert [e["path"] for e in errors_for(result, "evidence")] == ["lessons[0].evidence[0]"]
    assert "dummy" not in result.raw.decode("utf-8")


@needs_git
def test_commit_evidence(sdd_export, tmp_path):
    root = project(tmp_path, git=True)
    git_run(root, "add", "-A")
    git_run(root, "commit", "--quiet", "-m", "first")
    head = git_run(root, "rev-parse", "HEAD").strip()

    for good in (head, head[:7], head[:12]):
        data = draft(lessons=[lesson("atomic-write", evidence=[f"commit:{good}"])])
        assert validate(sdd_export, root, data).code == 0, good
    for bad in ("0" * 40, head.upper()[:10], head[:6], head + "0"):
        data = draft(lessons=[lesson("atomic-write", evidence=[f"commit:{bad}"])])
        assert checks(validate(sdd_export, root, data)) == ["evidence"], bad


def test_unsupported(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft()
    data["features"][0]["requirements"][0]["evidence"] = []
    data["principles"][0]["evidence"] = []
    result = validate(sdd_export, root, data)

    paths = [e["path"] for e in errors_for(result, "unsupported")]
    assert paths == ["features[0].requirements[0]", "principles[0]"]


def test_pending_without_evidence_is_fine(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft()
    data["features"][0]["requirements"][0].update(status="pending", evidence=[])
    result = validate(sdd_export, root, data)

    assert result.code == 0
    assert result.out["counts"]["pending"] == 1


def test_spec_check(sdd_export, tmp_path):
    root = spec_project(tmp_path)
    ok = spec_draft()
    assert validate(sdd_export, root, ok).code == 0

    for source in ("spec", "mixed"):
        data = spec_draft()
        data["features"][0].update(source=source, spec="specs/009-gone/spec.md")
        assert [e["path"] for e in errors_for(validate(sdd_export, root, data), "spec")] == ["features[0].spec"]
        data["features"][0]["spec"] = None
        assert "features[0].spec" in [e["path"] for e in validate(sdd_export, root, data).out["errors"]]
        data["features"][0]["spec"] = "specs/001-deploy"
        assert [e["path"] for e in errors_for(validate(sdd_export, root, data), "spec")] == ["features[0].spec"]

    for source in ("code", "maintainer"):
        data = spec_draft()
        data["features"][0].update(source=source, spec=None)
        assert validate(sdd_export, root, data).code == 0


def test_dependency_check(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(features=[
        feature("a", depends_on=["b"]),
        feature("b", depends_on=["b"], requirements=[requirement("b-one")]),
        feature("c", depends_on=["a", "nowhere"], requirements=[requirement("c-one")]),
    ])
    result = validate(sdd_export, root, data)

    paths = [e["path"] for e in errors_for(result, "dependency")]
    assert paths == ["features[0].depends_on[0]", "features[1].depends_on[0]", "features[2].depends_on[1]"]


def test_scope_check(sdd_export, tmp_path):
    root = project(tmp_path)

    assert validate(sdd_export, root, draft(scope={"coverage": "partial", "included": ["src"]})).code == 0
    assert validate(sdd_export, root, draft(scope={"coverage": "partial", "included": ["src", "README.md"]})).code == 0
    for scope, path in (
        ({"coverage": "partial", "included": []}, "scope.included"),
        ({"coverage": "partial", "included": ["lib"]}, "scope.included[0]"),
        ({"coverage": "partial", "included": ["/abs"]}, "scope.included[0]"),
        ({"coverage": "full", "included": ["src"]}, "scope.included"),
    ):
        result = validate(sdd_export, root, draft(scope=scope))
        assert path in [e["path"] for e in errors_for(result, "scope")], scope


def test_all_errors_at_once_sorted_by_path(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(features=[feature("a"), feature("b", requirements=[requirement("b-one")])])
    data["lessons"][0]["kind"] = "tip"
    data["features"][1]["requirements"][0]["evidence"] = []
    data["features"][0]["summary"] = ""
    data["principles"][0]["origin"] = 5
    data["features"] += [feature(f"f{n}", requirements=[requirement(f"f{n}-one")]) for n in range(2, 11)]
    data["features"][10]["source"] = "guess"
    result = validate(sdd_export, root, data)

    paths = [e["path"] for e in result.out["errors"]]
    assert paths == ["features[0].summary", "features[1].requirements[0]", "features[10].source",
                     "lessons[0].kind", "principles[0].origin"]


def test_counts(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(
        features=[feature("deploy", requirements=[requirement("r1"), requirement("r2", status="pending", evidence=[])])],
        discarded=[discarded("old")],
    )
    counts = validate(sdd_export, root, data).out["counts"]

    assert counts == {"principles": 1, "features": 1, "requirements": 2, "lessons": 1, "discarded": 1,
                      "pending": 1, "inherited": 0, "new": 5}


def test_validate_writes_nothing(sdd_export, tmp_path):
    root = spec_project(tmp_path)
    before = tree_snapshot(root)

    validate(sdd_export, root, spec_draft())
    validate(sdd_export, root, "garbage")

    assert tree_snapshot(root) == before


def test_validate_stops_on_project_state(sdd_export, tmp_path):
    root = project(tmp_path)
    (root / ".sdd-export").mkdir()
    (root / ".sdd-export" / "notes.txt").write_text("x\n")
    result = validate(sdd_export, root, draft())

    assert result.code == 3
    assert result.out["reason"] == "conflict"


# =================================================================== diff


def nutrients_of(data: dict) -> dict:
    return {"tool": "sdd-export", "schema": 1, "exported_at": "2026-11-20", **data}


def test_diff_without_existing_nutrients(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(discarded=[discarded("old")])
    diff = validate(sdd_export, root, data).out["diff"]

    assert diff["base"] == "none"
    assert diff["generation"] is None and diff["scope"] is None
    assert diff["removed"] == [] and diff["changed"] == [] and diff["order_changed"] is False
    assert [(a["section"], a["id"]) for a in diff["added"]] == [
        ("principles", "keep-small"), ("features", "deploy"), ("requirements", "deploy-one"),
        ("lessons", "atomic-write"), ("discarded", "old"),
    ]
    assert diff["added"][1]["title"] == "功能 deploy"
    assert diff["added"][2]["title"] == "需求 deploy-one 的可驗收行為。"
    assert list(diff) == ["base", "generation", "scope", "added", "removed", "changed", "order_changed"]


def test_diff_is_a_pure_function(sdd_export):
    old = nutrients_of(draft())
    new = copy.deepcopy(old)
    new["features"][0]["requirements"].append(requirement("deploy-two", text="第一行\n第二行"))
    new["lessons"] = []
    new["principles"][0]["text"] = "新的原則文字。"
    new["scope"] = {"coverage": "partial", "included": ["src"]}
    new["generation"] = 2

    diff = sdd_export.compute_diff(old, new)

    assert diff["base"] == "nutrients"
    assert diff["generation"] == {"from": 1, "to": 2}
    assert diff["scope"] == {"from": {"coverage": "full", "included": []}, "to": {"coverage": "partial", "included": ["src"]}}
    assert diff["added"] == [{"section": "requirements", "id": "deploy-two", "title": "第一行"}]
    assert diff["removed"] == [{"section": "lessons", "id": "atomic-write", "title": "教訓 atomic-write"}]
    assert diff["changed"] == [
        {"section": "principles", "id": "keep-small",
         "fields": [{"field": "text", "from": "每個功能 MUST 簡單。", "to": "新的原則文字。"}]},
    ]
    assert sdd_export.compute_diff(None, new)["base"] == "none"


def test_diff_title_is_cut_at_80_characters(sdd_export):
    old = nutrients_of(draft())
    new = copy.deepcopy(old)
    new["features"][0]["requirements"].append(requirement("long", text="長" * 100 + "\n第二行"))

    assert sdd_export.compute_diff(old, new)["added"][0]["title"] == "長" * 80


def test_diff_requirement_moved_to_another_feature(sdd_export):
    old = nutrients_of(draft(features=[feature("a", requirements=[requirement("r1"), requirement("r2")]),
                                       feature("b", requirements=[requirement("r3")])]))
    new = copy.deepcopy(old)
    moved = new["features"][0]["requirements"].pop(1)
    new["features"][1]["requirements"].append(moved)

    diff = sdd_export.compute_diff(old, new)

    assert diff["changed"] == [{"section": "requirements", "id": "r2", "fields": [{"field": "feature", "from": "a", "to": "b"}]}]
    assert diff["added"] == [] and diff["removed"] == []


def test_diff_order_changed(sdd_export):
    old = nutrients_of(draft(features=[feature("a"), feature("b", requirements=[requirement("b-one")])]))
    new = copy.deepcopy(old)
    new["features"].reverse()

    diff = sdd_export.compute_diff(old, new)

    assert diff["order_changed"] is True
    assert diff["changed"] == []


def test_diff_lists_changes_of_features_and_discarded(sdd_export):
    old = nutrients_of(draft(discarded=[discarded("old")]))
    new = copy.deepcopy(old)
    new["features"][0]["depends_on"] = []
    new["features"][0]["summary"] = "新的摘要。"
    new["discarded"][0]["reason"] = "新的理由"

    diff = sdd_export.compute_diff(old, new)

    assert diff["changed"] == [
        {"section": "features", "id": "deploy", "fields": [{"field": "summary", "from": "維護者可以使用 deploy。", "to": "新的摘要。"}]},
        {"section": "discarded", "id": "old", "fields": [{"field": "reason", "from": "維護者決定捨棄", "to": "新的理由"}]},
    ]


def test_diff_with_no_difference(sdd_export):
    old = nutrients_of(draft())

    diff = sdd_export.compute_diff(old, copy.deepcopy(old))

    assert (diff["added"], diff["removed"], diff["changed"], diff["order_changed"]) == ([], [], [], False)
    assert diff["generation"] is None and diff["scope"] is None


def test_validate_diffs_against_the_existing_nutrients(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    changed = draft()
    changed["lessons"] = []
    diff = validate(sdd_export, root, changed).out["diff"]

    assert diff["base"] == "nutrients"
    assert diff["removed"] == [{"section": "lessons", "id": "atomic-write", "title": "教訓 atomic-write"}]


# ================================================================== write


def read_export(root: Path, name: str) -> bytes:
    return (root / ".sdd-export" / name).read_bytes()


def test_write_touches_only_the_export_folder(sdd_export, tmp_path, fixed_day):
    root = spec_project(tmp_path, git=HAS_GIT)
    before = tree_snapshot(root)
    result = write_ok(sdd_export, root, spec_draft(), expect="none")

    changes = tree_changes(before, tree_snapshot(root))
    assert changes["removed"] == [] and changes["changed"] == []
    assert changes["added"] == [".sdd-export", ".sdd-export/.gitattributes", ".sdd-export/README.md",
                                ".sdd-export/nutrients.json"]
    out = result.out
    assert list(out) == ["written", "created", "state", "generation", "counts", "diff"]
    assert out["written"] == [".sdd-export/nutrients.json", ".sdd-export/README.md", ".sdd-export/.gitattributes"]
    assert out["created"] is True
    assert out["generation"] == 1
    assert out["counts"]["features"] == 3
    assert out["diff"]["base"] == "none"
    assert out["state"] == run_export(sdd_export, root, "check").out["state"]


def test_only_write_creates_files(sdd_export, tmp_path):
    root = spec_project(tmp_path)
    before = tree_snapshot(root)
    run_export(sdd_export, root, "check")
    run_export(sdd_export, root, "files")
    run_export(sdd_export, root, "files", "--scope", "src")
    validate(sdd_export, root, spec_draft())
    assert tree_snapshot(root) == before

    run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(spec_draft()))
    assert tree_snapshot(root) != before


def test_written_nutrients(sdd_export, tmp_path, fixed_day):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    raw = read_export(root, "nutrients.json")

    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    parsed = json.loads(raw)
    assert list(parsed)[:6] == ["tool", "schema", "generation", "project", "exported_at", "language"]
    assert (parsed["tool"], parsed["schema"], parsed["exported_at"]) == ("sdd-export", 1, "2026-11-20")
    assert raw == sdd_export.serialize(parsed, "nutrients")
    assert read_export(root, ".gitattributes") == GITATTRIBUTES.encode("utf-8")


def test_existing_gitattributes_is_left_alone(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    attributes = root / ".sdd-export" / ".gitattributes"
    attributes.write_text("* text eol=lf\n# mine\n")

    result = write_ok(sdd_export, root, draft())

    assert attributes.read_text() == "* text eol=lf\n# mine\n"
    assert result.out["written"] == [".sdd-export/nutrients.json", ".sdd-export/README.md"]
    assert result.out["created"] is False
    assert run_export(sdd_export, root, "check").out["gitattributes"] == "edited"


MARKER = __import__("re").compile(
    r"^<!-- Generated by sdd-export from nutrients\.json; do not edit\. source-sha256: ([0-9a-f]{64}) view-sha256: ([0-9a-f]{64}) -->$"
)


def test_readme_marker_and_hashes(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    readme = read_export(root, "README.md").decode("utf-8")
    first, rest = readme.split("\n", 1)
    match = MARKER.match(first)

    assert match, first
    assert match.group(1) == hashlib.sha256(read_export(root, "nutrients.json")).hexdigest()
    assert match.group(2) == hashlib.sha256(rest.encode("utf-8")).hexdigest()


def full_draft() -> dict:
    features = [
        feature("deploy", requirements=[
            requirement("deploy-story", kind="story"),
            requirement("deploy-one"),
            requirement("deploy-edge", kind="edge-case", status="pending", evidence=[]),
            requirement("deploy-sc", kind="success-criterion"),
            requirement("deploy-assume", kind="assumption", source="maintainer", evidence=["maintainer"]),
        ]),
        feature("status", depends_on=["deploy"], requirements=[requirement("status-one")]),
    ]
    lessons = [lesson("why-json"), lesson("atomic-write", kind="pitfall"), lesson("no-symlink", kind="reversed")]
    return draft(features=features, lessons=lessons, discarded=[discarded("old-idea", kind="doubt", reason="不是問題 | 沒影響")])


def test_readme_structure(sdd_export, tmp_path, fixed_day):
    root = project(tmp_path)
    write_ok(sdd_export, root, full_draft())
    readme = read_export(root, "README.md").decode("utf-8")
    lines = readme.split("\n")

    assert lines[1] == "# Nutrients: my-tool"
    order = [readme.index(h) for h in ("\n## Principles\n", "\n## Features\n", "\n## Lessons\n", "\n## Discarded\n")]
    assert order == sorted(order)
    for needle in ("2026-11-20", "Generation", "Scope", "full"):
        assert needle in readme.split("## Principles")[0], needle
    features = readme[readme.index("\n## Features\n"):readme.index("\n## Lessons\n")]
    assert features.index("功能 deploy") < features.index("功能 status")
    for rid in ("deploy-story", "deploy-one", "deploy-edge", "deploy-sc", "deploy-assume", "status-one"):
        assert f"`{rid}`" in features
    edge_line = next(line for line in features.split("\n") if "`deploy-edge`" in line)
    assert "(pending)" in edge_line
    one_line = next(line for line in features.split("\n") if "`deploy-one`" in line)
    assert "(pending)" not in one_line
    assert "src/app.py" in features
    lessons = readme[readme.index("\n## Lessons\n"):readme.index("\n## Discarded\n")]
    assert lessons.index("Decisions") < lessons.index("Pitfalls") < lessons.index("Reversed approaches")
    discarded_part = readme[readme.index("\n## Discarded\n"):]
    assert "| `old-idea` | doubt | 1 | 1 |" in discarded_part
    assert "不是問題 \\| 沒影響" in discarded_part


def test_readme_is_deterministic(sdd_export):
    data = nutrients_of(full_draft())

    assert sdd_export.render_readme(data) == sdd_export.render_readme(copy.deepcopy(data))
    assert isinstance(sdd_export.render_readme(data), bytes)


def test_check_after_write(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, full_draft())
    out = run_export(sdd_export, root, "check").out

    assert (out["export_dir"], out["nutrients"], out["view"]) == ("ours", "unchanged", "current")


def test_expect_must_match(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    before = tree_snapshot(root)

    for expect in ("none", "0" * 64):
        result = run_export(sdd_export, root, "write", "--expect", expect, stdin=dump(draft(project="x")))
        assert result.code == 1
        assert result.out["reason"] == "changed"
        assert result.out["error"] == CHANGED_ERROR
        assert tree_snapshot(root) == before


def test_expect_none_needs_a_missing_folder(sdd_export, tmp_path):
    root = project(tmp_path)

    assert run_export(sdd_export, root, "write", "--expect", "0" * 64, stdin=dump(draft())).out["reason"] == "changed"
    assert not (root / ".sdd-export").exists()


@pytest.mark.parametrize("bad", ["broken", "secret"])
def test_write_validates_again(sdd_export, tmp_path, bad):
    root = project(tmp_path)
    data = draft()
    if bad == "broken":
        data["language"] = "en"
    else:
        data["lessons"][0]["text"] = "password=abc123"
    result = run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(data))

    assert result.code == 1
    assert result.out["reason"] == ("invalid" if bad == "broken" else "secret")
    assert result.out["errors"]
    assert not (root / ".sdd-export").exists()


def test_write_stops_on_conflict(sdd_export, tmp_path):
    root = project(tmp_path)
    (root / ".sdd-export").mkdir()
    (root / ".sdd-export" / "notes.txt").write_text("mine\n")
    before = tree_snapshot(root)
    result = run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(draft()))

    assert result.code == 3
    assert result.out["reason"] == "conflict"
    assert result.out["conflicts"] == [".sdd-export/notes.txt"]
    assert tree_snapshot(root) == before


def test_write_into_an_existing_empty_folder(sdd_export, tmp_path):
    root = project(tmp_path)
    (root / ".sdd-export").mkdir()

    result = write_ok(sdd_export, root, draft(), expect="none")

    assert result.out["created"] is False


def failing_replace(sdd_export, monkeypatch, fail_on: int):
    real = os.replace
    calls = {"n": 0}

    def replace(src, dst):
        calls["n"] += 1
        if calls["n"] == fail_on:
            raise OSError(28, "No space left on device")
        return real(src, dst)

    monkeypatch.setattr(sdd_export.os, "replace", replace)


def leftovers(root: Path) -> list[str]:
    folder = root / ".sdd-export"
    return sorted(p.name for p in folder.iterdir() if ".tmp-" in p.name) if folder.is_dir() else []


def test_second_replace_fails(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    state = run_export(sdd_export, root, "check").out["state"]
    new = draft(project="renamed")
    failing_replace(sdd_export, monkeypatch, fail_on=2)

    result = run_export(sdd_export, root, "write", "--expect", state, stdin=dump(new))

    assert result.code == 1
    assert result.out["reason"] == "os-error"
    assert result.out["error"].startswith("could not write .sdd-export/: ")
    assert json.loads(read_export(root, "nutrients.json"))["project"] == "renamed"
    assert leftovers(root) == []
    monkeypatch.undo()
    out = run_export(sdd_export, root, "check").out
    assert out["view"] == "stale"
    assert out["nutrients"] == "edited"


def test_writing_a_temporary_file_fails(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    old = read_export(root, "nutrients.json")
    state = run_export(sdd_export, root, "check").out["state"]
    real_open = os.open

    def broken_open(path, flags, *args, **kwargs):
        if ".tmp-" in str(path):
            raise OSError(13, "Permission denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(sdd_export.os, "open", broken_open)
    result = run_export(sdd_export, root, "write", "--expect", state, stdin=dump(draft(project="renamed")))

    assert result.out["reason"] == "os-error"
    assert read_export(root, "nutrients.json") == old
    assert leftovers(root) == []


def test_new_folder_is_removed_after_a_failure(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    failing_replace(sdd_export, monkeypatch, fail_on=1)

    result = run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(draft()))

    assert result.out["reason"] == "os-error"
    assert not (root / ".sdd-export").exists()


def test_existing_empty_folder_is_kept_after_a_failure(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path)
    (root / ".sdd-export").mkdir()
    failing_replace(sdd_export, monkeypatch, fail_on=1)

    result = run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(draft()))

    assert result.out["reason"] == "os-error"
    assert (root / ".sdd-export").is_dir()
    assert list((root / ".sdd-export").iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32" or IS_ROOT, reason="needs POSIX permissions and a non-root user")
def test_read_only_project(sdd_export, tmp_path):
    root = project(tmp_path)
    root.chmod(0o555)
    try:
        result = run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(draft()))
        exists = (root / ".sdd-export").exists()
    finally:
        root.chmod(0o755)

    assert result.code == 1
    assert result.out["reason"] == "os-error"
    assert not exists


def test_read_only_project_stand_in(sdd_export, tmp_path, monkeypatch):
    """The same situation on every platform: creating the folder is refused."""
    root = project(tmp_path)
    real_mkdir = Path.mkdir

    def refuse(self, *args, **kwargs):
        if self.name == ".sdd-export":
            raise PermissionError(13, "Permission denied")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse)
    result = run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(draft()))

    assert result.out["reason"] == "os-error"
    assert not (root / ".sdd-export").exists()


def test_same_draft_same_day_same_bytes(sdd_export, tmp_path, fixed_day):
    root = project(tmp_path)
    first = write_ok(sdd_export, root, full_draft(), expect="none")
    files = {name: read_export(root, name) for name in ("nutrients.json", "README.md", ".gitattributes")}

    second = write_ok(sdd_export, root, full_draft(), expect=first.out["state"])

    assert {name: read_export(root, name) for name in files} == files
    assert second.out["state"] == first.out["state"]


def test_write_reads_the_draft_only_from_stdin(sdd_export, tmp_path):
    root = project(tmp_path)
    (root / "draft.json").write_text(dump(draft()), "utf-8")

    for argv in (["write", "--expect", "none", "draft.json"], ["write", "--expect", "none", "--input", "draft.json"]):
        assert run_export(sdd_export, root, *argv).out["reason"] == "usage"


# ========================================================= files, inventory

DEPENDENCY_DIRS = ["node_modules", "bower_components", "jspm_packages", "vendor", ".venv", "venv", "Pods", "Carthage",
                   ".terraform", ".bundle"]
BUILD_DIRS = ["dist", "build", "target", "bin", "obj", "out", ".next", ".nuxt", ".svelte-kit", ".output", "coverage",
              "htmlcov", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".gradle",
              ".cache", ".parcel-cache", ".turbo", ".eggs", "my_pkg.egg-info"]
TOOLING_DIRS = [".git", ".idea", ".vscode", ".claude", ".sdd-export", ".sdd-rebuild", ".specify"]
GENERATED_NAMES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json", "uv.lock", "poetry.lock",
                   "Pipfile.lock", "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock", "packages.lock.json",
                   "app.min.js", "style.min.css", "app.js.map"]


def files_of(result) -> list[str]:
    return [entry["path"] for entry in result.out["files"]]


def skipped_only(result, **expected) -> None:
    skipped = result.out["skipped"]
    assert list(skipped) == ["ignored", "dependency", "build", "tooling", "generated", "secret", "binary", "large"]
    for key, value in skipped.items():
        assert value == expected.get(key, 0), (key, skipped)


@pytest.mark.parametrize("name", DEPENDENCY_DIRS)
def test_dependency_folders(sdd_export, tmp_path, name):
    root = project(tmp_path, files={f"{name}/x/index.js": "x\n", f"src/{name}/y.js": "y\n"})
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == ["README.md", "src/app.py"]
    skipped_only(result, dependency=2)


@pytest.mark.parametrize("name", BUILD_DIRS)
def test_build_folders(sdd_export, tmp_path, name):
    root = project(tmp_path, files={f"{name}/app.js": "x\n"})
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == ["README.md", "src/app.py"]
    skipped_only(result, build=1)


@pytest.mark.parametrize("name", [name for name in TOOLING_DIRS if name != ".sdd-export"])
def test_tooling_folders_at_the_top(sdd_export, tmp_path, name):
    root = project(tmp_path, files={f"{name}/notes.md": "x\n", f"src/{name}/kept.md": "kept\n"})
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == sorted(["README.md", "src/app.py", f"src/{name}/kept.md"])
    skipped_only(result, tooling=1)


def test_the_export_folder_is_not_read(sdd_export, tmp_path):
    """.sdd-export/ holding anything else is a conflict; holding the nutrients, it is tooling."""
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == ["README.md", "src/app.py"]
    skipped_only(result, tooling=1)


def test_the_constitution_is_readable(sdd_export, tmp_path):
    root = project(tmp_path, constitution="# C\n", files={".specify/templates/t.md": "t\n"})
    result = run_export(sdd_export, root, "files")

    assert ".specify/memory/constitution.md" in files_of(result)
    assert ".specify/templates/t.md" not in files_of(result)
    skipped_only(result, tooling=1)


@pytest.mark.parametrize("name", GENERATED_NAMES)
def test_generated_files(sdd_export, tmp_path, name):
    root = project(tmp_path, files={f"web/{name}": "x\n"})
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == ["README.md", "src/app.py"]
    skipped_only(result, generated=1)


def test_secret_files_are_listed_and_never_opened(sdd_export, tmp_path, monkeypatch):
    root = project(tmp_path, files={".env": "API_KEY=dummy\n", ".env.example": "API_KEY=sample\n",
                                    "config/.ssh/id_rsa": "-----BEGIN RSA PRIVATE KEY-----\n", "keys/server.pem": "x\n"})
    opened: list[str] = []
    import builtins
    import io as io_module

    real_open, real_io_open, real_os_open = builtins.open, io_module.open, os.open

    def spy(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def os_spy(file, *args, **kwargs):
        opened.append(str(file))
        return real_os_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io_module, "open", spy)
    monkeypatch.setattr(os, "open", os_spy)
    result = run_export(sdd_export, root, "files")
    check = run_export(sdd_export, root, "check")
    monkeypatch.undo()

    secret = [".env", ".env.example", "config/.ssh/id_rsa", "keys/server.pem"]
    assert result.out["secret_files"] == secret
    assert check.out["inventory"]["secret_files"] == secret
    skipped_only(result, secret=4)
    for name in secret:
        assert not any(path.replace("\\", "/").endswith(name) for path in opened), (name, opened)
    text = result.raw.decode("utf-8") + check.raw.decode("utf-8")
    assert "dummy" not in text and "sample" not in text


@pytest.mark.skipif(sys.platform == "win32" or IS_ROOT, reason="needs POSIX permissions and a non-root user")
def test_unreadable_secret_files_do_not_matter(sdd_export, tmp_path):
    root = project(tmp_path, files={".env": "API_KEY=dummy\n"})
    (root / ".env").chmod(0)
    try:
        result = run_export(sdd_export, root, "files")
    finally:
        (root / ".env").chmod(0o644)

    assert result.code == 0
    assert result.out["secret_files"] == [".env"]


def test_secret_hits_give_only_path_and_line(sdd_export, tmp_path):
    root = project(tmp_path, files={"src/settings.py": 'DEBUG = True\npassword = "hunter2"\n'})
    result = run_export(sdd_export, root, "files")

    assert result.out["secret_hits"] == [{"path": "src/settings.py", "line": 2}]
    assert "hunter2" not in result.raw.decode("utf-8")


@pytest.mark.parametrize("name, content", [("logo.png", b"PNG"), ("font.woff2", b"x"), ("lib.so", b"x"),
                                           ("doc.pdf", b"x"), ("data.sqlite", b"x"), ("archive.zip", b"x"),
                                           ("blob.dat", b"abc\x00def")])
def test_binary_files(sdd_export, tmp_path, name, content):
    root = project(tmp_path, files={f"assets/{name}": content})
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == ["README.md", "src/app.py"]
    skipped_only(result, binary=1)


def test_large_files(sdd_export, tmp_path):
    mib = 1024 * 1024
    root = project(tmp_path, files={"data/big.txt": b"a" * (mib + 1), "data/edge.txt": b"a" * mib})
    result = run_export(sdd_export, root, "files")

    assert "data/edge.txt" in files_of(result)
    assert "data/big.txt" not in files_of(result)
    skipped_only(result, large=1)


@needs_git
def test_ignored_files_in_a_git_repository(sdd_export, tmp_path):
    root = project(tmp_path, git=True, files={".gitignore": "secret-notes/\n*.log\n", "secret-notes/a.md": "x\n",
                                               "debug.log": "x\n"})
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == [".gitignore", "README.md", "src/app.py"]
    assert result.out["skipped"]["ignored"] == 2
    assert run_export(sdd_export, root, "check").out["inventory"]["ignore_source"] == "git"


@needs_git
def test_git_and_plain_folder_agree_without_gitignore(sdd_export, tmp_path):
    tree = {"node_modules/a/index.js": "x\n", "node_modules/b/index.js": "y\n", "dist/app.js": "z\n",
            "web/package-lock.json": "{}\n", ".env": "A=b\n", "img/logo.png": "png", "lib/core.py": "core\n",
            ".specify/memory/constitution.md": "c\n", ".specify/templates/t.md": "t\n"}
    plain = project(tmp_path, "plain", files=tree)
    repo = project(tmp_path, "repo", files=tree, git=True)

    a, b = run_export(sdd_export, plain, "files"), run_export(sdd_export, repo, "files")

    assert a.out == b.out
    assert run_export(sdd_export, plain, "check").out["inventory"]["ignore_source"] == "none"
    ia = run_export(sdd_export, plain, "check").out["inventory"]
    ib = run_export(sdd_export, repo, "check").out["inventory"]
    assert {k: v for k, v in ia.items() if k != "ignore_source"} == {k: v for k, v in ib.items() if k != "ignore_source"}


def can_symlink(tmp_path: Path) -> bool:
    try:
        (tmp_path / "probe-link").symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        return False
    (tmp_path / "probe-link").unlink()
    return True


def test_symlinks(sdd_export, tmp_path):
    if not can_symlink(tmp_path):
        pytest.skip("this platform cannot create symbolic links here")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "o.txt").write_text("outside\n")
    root = project(tmp_path)
    (root / "link-out.txt").symlink_to(outside / "o.txt")
    (root / "link-dir").symlink_to(root / "src", target_is_directory=True)
    (root / "link-in.txt").symlink_to(root / "README.md")
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == ["README.md", "link-in.txt", "src/app.py"]
    assert result.out["skipped"]["ignored"] == 2


def test_names_are_compared_in_lowercase(sdd_export, tmp_path):
    root = project(tmp_path, files={"Node_Modules/x.js": "x\n", "DIST/a.js": "a\n", "web/Package-Lock.JSON": "{}\n",
                                    "img/LOGO.PNG": "p"})
    result = run_export(sdd_export, root, "files")

    assert files_of(result) == ["README.md", "src/app.py"]
    skipped_only(result, dependency=1, build=1, generated=1, binary=1)


def test_files_with_scope(sdd_export, tmp_path):
    root = spec_project(tmp_path, files={"src/api/routes.py": "r\n", "src/api/settings.py": "token = abc\n",
                                         "src/api/.env": "A=b\n", "src/api/dist/x.js": "x\n", "lib/x.py": "x\n"})
    result = run_export(sdd_export, root, "files", "--scope", "src/api", "--scope", "lib/x.py")

    assert result.code == 0
    assert result.out["scope"] == ["lib/x.py", "src/api"]
    assert files_of(result) == [".specify/memory/constitution.md", "lib/x.py", "specs/001-deploy/spec.md",
                                "specs/002-status/spec.md", "specs/003-remove/spec.md", "src/api/routes.py",
                                "src/api/settings.py"]
    assert result.out["secret_hits"] == [{"path": "src/api/settings.py", "line": 1}]
    assert result.out["secret_files"] == ["src/api/.env"]
    skipped_only(result, build=1, secret=1)
    assert list(result.out) == ["scope", "too_large", "files", "secret_hits", "skipped", "secret_files"]


def test_files_without_scope(sdd_export, tmp_path):
    root = project(tmp_path)
    result = run_export(sdd_export, root, "files")

    assert result.out["scope"] == []
    assert result.out["files"] == [{"path": "README.md", "bytes": 10}, {"path": "src/app.py", "bytes": 12}]


@pytest.mark.parametrize("scope", ["nowhere", "../outside", "/abs/path", "node_modules", "node_modules/x", ".env",
                                   ".git", "dist/a.js"])
def test_bad_scopes(sdd_export, tmp_path, scope):
    root = project(tmp_path, files={"node_modules/x/i.js": "x\n", ".env": "A=b\n", "dist/a.js": "a\n"})
    (tmp_path / "outside").mkdir()
    result = run_export(sdd_export, root, "files", "--scope", scope)

    assert result.code == 1
    assert result.out["reason"] == "usage"
    assert result.out["error"]


def many_files(count: int, folder: str = "src") -> dict[str, str]:
    return {f"{folder}/f{n:05d}.txt": "x" for n in range(count)}


def test_too_many_files(sdd_export, tmp_path):
    root = project(tmp_path, files={**many_files(1499, "src"), "lib/a.txt": "x"})
    # README.md + src/app.py + 1499 + 1 = 1502 readable files
    check = run_export(sdd_export, root, "check").out["inventory"]
    whole = run_export(sdd_export, root, "files")
    narrow = run_export(sdd_export, root, "files", "--scope", "lib")

    assert check["too_large"] is True and check["files"] == 1502
    assert whole.out["too_large"] is True and whole.out["files"] == [] and whole.out["secret_hits"] == []
    assert narrow.out["too_large"] is False and files_of(narrow) == ["lib/a.txt"]


def test_exactly_1500_files_is_not_too_large(sdd_export, tmp_path):
    root = project(tmp_path, files=many_files(1498))

    inventory = run_export(sdd_export, root, "check").out["inventory"]
    assert inventory["files"] == 1500 and inventory["too_large"] is False


def test_too_many_bytes(sdd_export, tmp_path):
    mib = 1024 * 1024
    files = {f"data/part{n}.txt": b"a" * mib for n in range(10)}
    root = project(tmp_path, files=files)
    inventory = run_export(sdd_export, root, "check").out["inventory"]
    assert inventory["bytes"] > 10 * mib and inventory["too_large"] is True

    exact = make_old_project(tmp_path, "exact", files={f"data/part{n}.txt": b"a" * mib for n in range(10)})
    inventory = run_export(sdd_export, exact, "check").out["inventory"]
    assert inventory["bytes"] == 10 * mib and inventory["too_large"] is False


MANIFESTS = ["package.json", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
             "build.gradle.kts", "App.csproj", "App.sln", "composer.json", "Gemfile", "mix.exs", "pubspec.yaml"]


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_two_areas_with_manifests_are_too_large(sdd_export, tmp_path, manifest):
    root = project(tmp_path, files={f"web/{manifest}": "x\n", f"api/{manifest}": "x\n"})
    inventory = run_export(sdd_export, root, "check").out["inventory"]

    assert inventory["too_large"] is True
    assert {area["path"]: area["manifests"] for area in inventory["areas"]}["web"] == [manifest]


def test_one_area_with_a_manifest_is_fine(sdd_export, tmp_path):
    root = project(tmp_path, files={"web/package.json": "{}\n", "web/sub/package.json": "{}\n"})

    assert run_export(sdd_export, root, "check").out["inventory"]["too_large"] is False


def test_areas(sdd_export, tmp_path):
    root = project(tmp_path, files={"pyproject.toml": "[project]\n", "docs/a.md": "aa\n", "node_modules/x.js": "x\n"})
    inventory = run_export(sdd_export, root, "check").out["inventory"]

    assert inventory["areas"] == [
        {"path": "docs", "files": 1, "bytes": 3, "manifests": []},
        {"path": "src", "files": 1, "bytes": 12, "manifests": []},
        {"path": ".", "files": 2, "bytes": 10 + 10, "manifests": ["pyproject.toml"]},
    ]
    assert list(inventory) == ["files", "bytes", "too_large", "ignore_source", "areas", "skipped", "secret_files"]


def test_inventory_matches_files(sdd_export, tmp_path):
    root = project(tmp_path, files={"node_modules/x.js": "x\n", ".env": "A=b\n", "docs/a.md": "a\n"})
    inventory = run_export(sdd_export, root, "check").out["inventory"]
    files = run_export(sdd_export, root, "files").out

    assert inventory["files"] == len(files["files"])
    assert inventory["bytes"] == sum(entry["bytes"] for entry in files["files"])
    assert inventory["skipped"] == files["skipped"]
    assert "files" not in json.dumps(inventory["areas"]).replace('"files"', "")


def test_files_and_check_read_only(sdd_export, tmp_path):
    root = project(tmp_path, files={"pyproject.toml": "[project]\n", "node_modules/x.js": "x\n"})
    before = tree_snapshot(root)

    run_export(sdd_export, root, "files")
    run_export(sdd_export, root, "files", "--scope", "src")
    run_export(sdd_export, root, "check")

    assert tree_snapshot(root) == before


@pytest.mark.parametrize("evidence", ["node_modules/x/index.js", "dist/app.js", "web/package-lock.json",
                                      "node_modules", "img/logo.png"])
def test_evidence_in_excluded_paths_is_refused(sdd_export, tmp_path, evidence):
    root = project(tmp_path, files={"node_modules/x/index.js": "x\n", "dist/app.js": "a\n",
                                    "web/package-lock.json": "{}\n", "img/logo.png": "p"})
    data = draft()
    data["lessons"][0]["evidence"] = [evidence]

    assert checks(validate(sdd_export, root, data)) == ["evidence"]


def test_quickstart_project(sdd_export, tmp_path):
    root = make_old_project(tmp_path, "quick", files={
        "src/app.py": "print('hi')\n", "README.md": "# quick\n", "node_modules/x/index.js": "x\n",
        "dist/app.js": "x\n", ".env": "API_KEY=dummy\n", "src/settings.py": 'password = "hunter2"\n',
    })
    check = run_export(sdd_export, root, "check").out
    files = run_export(sdd_export, root, "files").out

    skipped = check["inventory"]["skipped"]
    assert (skipped["dependency"], skipped["build"], skipped["secret"]) == (1, 1, 1)
    assert check["inventory"]["secret_files"] == [".env"]
    assert [entry["path"] for entry in files["files"]] == ["README.md", "src/app.py", "src/settings.py"]
    assert files["secret_hits"] == [{"path": "src/settings.py", "line": 1}]


def test_secret_scan_of_a_long_line_is_fast(sdd_export):
    """A 1 MiB line of letters (a readable file may hold one) is scanned in linear time."""
    import time

    started = time.monotonic()
    assert sdd_export.secret_lines("a" * (1024 * 1024)) == []
    assert sdd_export.secret_lines("x" * 500_000 + " https://u:p4ss@example.invalid") == [1]
    assert time.monotonic() - started < 5


# ================================================================ lessons


@pytest.mark.parametrize("kind", ["decision", "pitfall", "reversed"])
def test_lesson_kinds(sdd_export, tmp_path, kind):
    root = project(tmp_path)

    assert validate(sdd_export, root, draft(lessons=[lesson("x", kind=kind)])).code == 0


@pytest.mark.parametrize("kind", ["tip", "Decision", "", None, "lesson"])
def test_other_lesson_kinds_are_refused(sdd_export, tmp_path, kind):
    root = project(tmp_path)
    result = validate(sdd_export, root, draft(lessons=[lesson("x", kind=kind)]))

    assert result.code == 1
    assert [e["path"] for e in errors_for(result, "field")] == ["lessons[0].kind"]


@pytest.mark.parametrize("evidence", [["README.md"], ["maintainer"]])
def test_confirmed_lessons_need_evidence(sdd_export, tmp_path, evidence):
    root = project(tmp_path)

    assert validate(sdd_export, root, draft(lessons=[lesson("x", evidence=evidence)])).code == 0
    result = validate(sdd_export, root, draft(lessons=[lesson("x", evidence=[])]))
    assert [e["path"] for e in errors_for(result, "unsupported")] == ["lessons[0]"]
    assert validate(sdd_export, root, draft(lessons=[lesson("x", status="pending", evidence=[])])).code == 0


@needs_git
def test_lessons_from_git_history(sdd_export, tmp_path):
    root = project(tmp_path, git=True)
    git_run(root, "add", "-A")
    git_run(root, "commit", "--quiet", "-m", "first")
    head = git_run(root, "rev-parse", "HEAD").strip()

    assert validate(sdd_export, root, draft(lessons=[lesson("x", evidence=[f"commit:{head}"])])).code == 0
    missing = validate(sdd_export, root, draft(lessons=[lesson("x", evidence=["commit:" + "1" * 40])]))
    assert checks(missing) == ["evidence"]


def test_commit_evidence_outside_git(sdd_export, tmp_path):
    root = project(tmp_path)
    result = validate(sdd_export, root, draft(lessons=[lesson("x", evidence=["commit:abcdef1"])]))

    assert checks(result) == ["evidence"]


def test_no_lessons_is_valid_and_written(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft(lessons=[]))

    assert json.loads(read_export(root, "nutrients.json"))["lessons"] == []


def test_a_deleted_lesson_is_gone_after_writing(sdd_export, tmp_path):
    root = project(tmp_path)
    both = draft(lessons=[lesson("keep-me"), lesson("drop-me", kind="pitfall")])
    write_ok(sdd_export, root, both)
    fewer = draft(lessons=[lesson("keep-me")])

    diff = validate(sdd_export, root, fewer).out["diff"]
    write_ok(sdd_export, root, fewer)

    assert diff["removed"] == [{"section": "lessons", "id": "drop-me", "title": "教訓 drop-me"}]
    ids = [item["id"] for item in json.loads(read_export(root, "nutrients.json"))["lessons"]]
    assert ids == ["keep-me"]


def test_lessons_refuse_code_blocks(sdd_export, tmp_path):
    root = project(tmp_path)
    result = validate(sdd_export, root, draft(lessons=[lesson("x", text="原因：\n```\nrm -rf x\n```")]))

    assert [e["path"] for e in errors_for(result, "code-block")] == ["lessons[0].text"]


# ================================================================ lineage


def lineage_project(tmp_path: Path, record: dict | None = None, name: str = "my-tool", **kwargs) -> Path:
    files = dict(kwargs.pop("files", {}) or {})
    files[".sdd-rebuild/lineage.json"] = json.dumps(record if record is not None else lineage_record(), ensure_ascii=False, indent=2) + "\n"
    specs = kwargs.pop("specs", {"001-deploy": SPEC_TEXT})
    return project(tmp_path, name, files=files, specs=specs, **kwargs)


def gen2_draft(**overrides) -> dict:
    """A draft that follows lineage_record(): deploy and its requirement inherited, the lesson kept, the discard kept."""
    deploy = feature("deploy", source="spec", spec="specs/001-deploy/spec.md",
                     requirements=[requirement("deploy-one", source="spec", evidence=["specs/001-deploy/spec.md"])])
    data = draft(
        generation=2,
        principles=[],
        features=[deploy],
        lessons=[lesson("atomic-write", kind="pitfall", evidence=[".sdd-rebuild/lineage.json"])],
        discarded=[discarded("deploy-symlink", discarded_in=2)],
    )
    data.update(overrides)
    return data


def test_lineage_none(sdd_export, tmp_path):
    out = run_export(sdd_export, project(tmp_path), "check").out

    assert (out["lineage"], out["generation"], out["lineage_content"]) == ("none", 1, None)


def test_lineage_present(sdd_export, tmp_path):
    root = lineage_project(tmp_path, specs={"001-deploy": SPEC_TEXT, "002-new": SPEC_TEXT})
    result = run_export(sdd_export, root, "check")

    assert result.code == 0, result.out
    out = result.out
    assert (out["lineage"], out["generation"]) == ("present", 2)
    assert out["lineage_content"] == lineage_record()
    assert out["specs"] == [
        {"dir": "specs/001-deploy", "spec": "specs/001-deploy/spec.md", "in_lineage": True},
        {"dir": "specs/002-new", "spec": "specs/002-new/spec.md", "in_lineage": False},
    ]
    assert out["lineage_missing_specs"] == []


def test_lineage_missing_specs(sdd_export, tmp_path):
    root = lineage_project(tmp_path, specs={})
    out = run_export(sdd_export, root, "check").out

    assert out["lineage_missing_specs"] == [{"id": "deploy", "spec_dir": "specs/001-deploy"}]


def test_existing_generation_differs(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    write_tree(root, {"specs/001-deploy/spec.md": SPEC_TEXT,
                      ".sdd-rebuild/lineage.json": json.dumps(lineage_record(), ensure_ascii=False)})
    out = run_export(sdd_export, root, "check").out

    assert (out["generation"], out["existing_generation"]) == (2, 1)


@pytest.mark.parametrize(
    "content, reason",
    [
        (b"\xff\xfe", "lineage-unreadable"),
        (b"[]", "lineage-unreadable"),
        (b"{broken", "lineage-unreadable"),
        (json.dumps({**lineage_record(), "schema": 2}).encode(), "lineage-newer"),
        (json.dumps({**lineage_record(), "tool": "sdd-export"}).encode(), "lineage-conflict"),
        (json.dumps({k: v for k, v in lineage_record().items() if k != "tool"}).encode(), "lineage-conflict"),
    ],
)
def test_lineage_cannot_be_used(sdd_export, tmp_path, content, reason):
    root = project(tmp_path, files={".sdd-rebuild/lineage.json": content})
    result = run_export(sdd_export, root, "check")

    assert result.code == 3
    assert result.out["reason"] == reason
    assert result.out["generation"] is None
    assert result.out["lineage_content"] is None
    assert result.out["error"] in result.err


def broken_lineage(change) -> dict:
    record = lineage_record()
    change(record)
    return record


INVALID_LINEAGES = [
    (lambda r: r.update(generation=3), "generation"),
    (lambda r: r.update(generation=1, source={**r["source"], "generation": 0}), "generation"),
    (lambda r: r["features"][0].update(origin=3), "features[0].origin"),
    (lambda r: r["features"][0].update(revised=[1]), "features[0].revised"),
    (lambda r: r["lessons"][0].update(id="deploy"), "lessons[0].id"),
    (lambda r: r["features"].insert(0, {**r["features"][0], "id": "first", "depends_on": ["deploy"],
                                          "spec_dir": "specs/000-first",
                                          "requirements": [{**r["features"][0]["requirements"][0], "id": "first-one"}]}),
     "features[0].depends_on[0]"),
    (lambda r: r["features"][0].update(spec_dir="specs/001-deploy/sub"), "features[0].spec_dir"),
    (lambda r: r["features"][0].update(spec_dir="other/001-deploy"), "features[0].spec_dir"),
    (lambda r: r["features"][0]["requirements"][0].update(status="confirmed"), "features[0].requirements[0].status"),
    (lambda r: r["lessons"][0].update(evidence=["README.md"]), "lessons[0].evidence"),
    (lambda r: r.update(rebuilt_at="yesterday"), "rebuilt_at"),
    (lambda r: r["discarded"][0].update(discarded_in=3), "discarded[0].discarded_in"),
    (lambda r: r.pop("source"), "source"),
]


@pytest.mark.parametrize("change, path", INVALID_LINEAGES)
def test_lineage_invalid(sdd_export, tmp_path, change, path):
    root = lineage_project(tmp_path, broken_lineage(change))
    result = run_export(sdd_export, root, "check")

    assert result.code == 3
    assert result.out["reason"] == "lineage-invalid"
    assert result.out["lineage"] == "invalid"
    assert result.out["generation"] is None
    assert path in [error["path"] for error in result.out["errors"]], result.out["errors"]


def test_lineage_accepts_rebuild_as_a_source(sdd_export, tmp_path):
    def change(record):
        record["features"][0]["source"] = "rebuild"
        record["features"][0]["spec"] = None
        record["features"][0]["requirements"][0]["source"] = "rebuild"

    root = lineage_project(tmp_path, broken_lineage(change))

    assert run_export(sdd_export, root, "check").out["lineage"] == "present"


def test_lineage_with_crlf_is_read(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    path = root / ".sdd-rebuild" / "lineage.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    out = run_export(sdd_export, root, "check").out
    assert (out["lineage"], out["generation"]) == ("present", 2)


def test_only_lineage_json_is_opened_in_sdd_rebuild(sdd_export, tmp_path, monkeypatch):
    root = lineage_project(tmp_path, files={".sdd-rebuild/notes.md": "x\n", ".sdd-rebuild/state.json": "{}\n"})
    import builtins
    import io as io_module

    opened: list[str] = []
    real_open = builtins.open

    def spy(file, *args, **kwargs):
        opened.append(str(file).replace("\\", "/"))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io_module, "open", spy)
    run_export(sdd_export, root, "check")
    validate(sdd_export, root, gen2_draft())
    monkeypatch.undo()

    in_rebuild = sorted({path.split(".sdd-rebuild/")[1] for path in opened if ".sdd-rebuild/" in path})
    assert in_rebuild == ["lineage.json"]


def test_check_with_lineage_reads_only(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    before = tree_snapshot(root)

    run_export(sdd_export, root, "check")

    assert tree_snapshot(root) == before


# ------------------------------------------------------- generation rules


def rule_errors(sdd_export, root: Path, data: dict, check: str) -> list[dict]:
    result = validate(sdd_export, root, data)
    return [error for error in result.out["errors"] if error["check"] == check]


def test_gen2_draft_follows_the_lineage(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    result = validate(sdd_export, root, gen2_draft())

    assert result.code == 0, result.out["errors"]
    assert result.out["counts"]["inherited"] == 3
    assert result.out["counts"]["new"] == 0


def test_rule_1_generation(sdd_export, tmp_path):
    root = lineage_project(tmp_path)

    assert rule_errors(sdd_export, root, gen2_draft(), "generation") == []
    data = gen2_draft(generation=3)
    assert [e["path"] for e in rule_errors(sdd_export, root, data, "generation")] == ["generation"]
    assert [e["path"] for e in rule_errors(sdd_export, project(tmp_path, "plain"), draft(generation=2), "generation")] == ["generation"]


@pytest.mark.parametrize("section", ["principles", "features", "requirements", "lessons"])
def test_rule_2_lineage_items_do_not_vanish(sdd_export, tmp_path, section):
    record = lineage_record(principles=[{k: v for k, v in principle("keep-small").items() if k not in ("status", "evidence")}])
    root = lineage_project(tmp_path, record)
    base = gen2_draft(principles=[principle("keep-small")])
    assert validate(sdd_export, root, base).code == 0

    data = copy.deepcopy(base)
    if section == "principles":
        data["principles"] = []
        gone = "keep-small"
    elif section == "features":
        data["features"] = [feature("other", origin=2, requirements=[requirement("deploy-one", source="spec",
                                                                                  evidence=["specs/001-deploy/spec.md"])])]
        gone = "deploy"
    elif section == "requirements":
        data["features"][0]["requirements"] = [requirement("deploy-two", origin=2)]
        gone = "deploy-one"
    else:
        data["lessons"] = []
        gone = "atomic-write"
    errors = rule_errors(sdd_export, root, data, "lineage-item-missing")

    assert len(errors) == 1 and gone in errors[0]["detail"]


def test_rule_2_kept_discarded_or_derived(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    discarded_lesson = gen2_draft(lessons=[], discarded=[discarded("deploy-symlink", discarded_in=2),
                                                          discarded("atomic-write", kind="lesson", discarded_in=2)])
    derived = gen2_draft(lessons=[lesson("write-safely", origin=2, kind="pitfall", derived_from=["atomic-write"])])

    assert validate(sdd_export, root, discarded_lesson).code == 0
    assert validate(sdd_export, root, derived).code == 0


def test_rule_3_origin_changed(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    data = gen2_draft()
    data["lessons"][0]["origin"] = 2

    assert [e["path"] for e in rule_errors(sdd_export, root, data, "origin-changed")] == ["lessons[0].origin"]


def test_rule_3_against_existing_nutrients(sdd_export, tmp_path):
    """An inherited item of the existing nutrients (origin below the generation) keeps its origin too."""
    root = lineage_project(tmp_path)
    earlier = gen2_draft(principles=[principle("hand-added", origin=1, evidence=["maintainer"])])
    (root / ".sdd-export").mkdir()
    (root / ".sdd-export" / "nutrients.json").write_bytes(sdd_export.serialize(nutrients_of(earlier), "nutrients"))
    assert run_export(sdd_export, root, "check").out["export_dir"] == "ours"
    data = gen2_draft(principles=[principle("hand-added", origin=2, evidence=["maintainer"])])

    assert validate(sdd_export, root, earlier).code == 0
    assert [e["path"] for e in rule_errors(sdd_export, root, data, "origin-changed")] == ["principles[0].origin"]


def test_rule_4_origin_unknown(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    data = gen2_draft(principles=[principle("from-nowhere", origin=1)])

    assert [e["path"] for e in rule_errors(sdd_export, root, data, "origin-unknown")] == ["principles[0].origin"]
    plain = project(tmp_path, "plain")
    assert [e["path"] for e in rule_errors(sdd_export, plain, draft(generation=1), "origin-unknown")] == []


def test_rule_5_revision_unmarked(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    data = gen2_draft()
    data["features"][0]["requirements"][0]["text"] = "改過的需求。"
    data["features"][0]["summary"] = "改過的摘要。"
    data["lessons"][0]["title"] = "改過的標題"

    paths = [e["path"] for e in rule_errors(sdd_export, root, data, "revision-unmarked")]
    assert paths == ["features[0].requirements[0].revised", "features[0].revised", "lessons[0].revised"]

    for item in (data["features"][0]["requirements"][0], data["features"][0], data["lessons"][0]):
        item["revised"] = [2]
    assert validate(sdd_export, root, data).code == 0


def test_rule_6_discard_lost(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    lost = gen2_draft(discarded=[])
    changed = gen2_draft(discarded=[discarded("deploy-symlink", discarded_in=2, reason="另一個理由")])

    assert [e["detail"] for e in rule_errors(sdd_export, root, lost, "discard-lost")][0].find("deploy-symlink") >= 0
    assert len(rule_errors(sdd_export, root, changed, "discard-lost")) == 1


def test_rule_6_against_existing_nutrients(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    earlier = gen2_draft(discarded=[discarded("deploy-symlink", discarded_in=2), discarded("old-doubt", kind="doubt",
                                                                                          origin=1, discarded_in=1)])
    path = root / ".sdd-export"
    path.mkdir()
    (path / "nutrients.json").write_bytes(sdd_export.serialize(nutrients_of(earlier), "nutrients"))
    assert run_export(sdd_export, root, "check").out["export_dir"] == "ours"

    assert len(rule_errors(sdd_export, root, gen2_draft(), "discard-lost")) == 1
    assert rule_errors(sdd_export, root, earlier, "discard-lost") == []


def test_rule_7_discarded_active(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(discarded=[discarded("deploy", kind="feature")])

    assert [e["path"] for e in rule_errors(sdd_export, root, data, "discarded-active")] == ["discarded[0].id"]


def test_rule_8_derived_unknown(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    good = gen2_draft(principles=[principle("merged", origin=2, derived_from=["deploy-symlink"])])
    bad = gen2_draft(principles=[principle("merged", origin=2, derived_from=["never-existed"])])

    assert validate(sdd_export, root, good).code == 0
    assert [e["path"] for e in rule_errors(sdd_export, root, bad, "derived-unknown")] == ["principles[0].derived_from[0]"]


def test_rule_8_keeps_sources_recorded_by_earlier_generations(sdd_export, tmp_path):
    record = lineage_record()
    record["features"][0]["requirements"][0]["derived_from"] = ["older-one"]
    root = lineage_project(tmp_path, record)
    data = gen2_draft()
    data["features"][0]["requirements"][0]["derived_from"] = ["older-one"]

    assert validate(sdd_export, root, data).code == 0
    data["features"][0]["derived_from"] = ["older-one"]
    assert [e["path"] for e in rule_errors(sdd_export, root, data, "derived-unknown")] == ["features[0].derived_from[0]"]


def test_rule_9_id_reused(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    data = gen2_draft(principles=[principle("deploy-symlink", origin=2)])

    errors = rule_errors(sdd_export, root, data, "id-reused")
    assert [e["path"] for e in errors] == ["principles[0].id"]


def test_rules_are_quiet_without_lineage_or_nutrients(sdd_export, tmp_path):
    root = project(tmp_path)
    result = validate(sdd_export, root, draft(discarded=[discarded("old")]))

    assert result.code == 0


def test_every_rule_violation_at_once(sdd_export, tmp_path):
    root = lineage_project(tmp_path)
    data = gen2_draft(lessons=[], discarded=[])
    data["features"][0]["origin"] = 2
    result = validate(sdd_export, root, data)

    assert {"lineage-item-missing", "origin-changed", "discard-lost"} <= set(checks(result))
    assert result.out["reason"] == "invalid"


# ---------------------------------------------------- three generations


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_bytes().decode("utf-8"))


def generation_project(tmp_path: Path, name: str, specs: list[str], lineage: str | None) -> Path:
    files = {f"specs/{spec}/spec.md": SPEC_TEXT for spec in specs}
    files[".specify/memory/constitution.md"] = "# Constitution\n"
    if lineage:
        files[".sdd-rebuild/lineage.json"] = (FIXTURES / lineage).read_bytes()
    return make_old_project(tmp_path, name, files=files)


def test_three_generations(sdd_export, tmp_path, fixed_day):
    first = generation_project(tmp_path, "gen1", ["001-deploy", "002-status"], None)
    assert run_export(sdd_export, first, "check").out["generation"] == 1
    write_ok(sdd_export, first, fixture("gen1-draft.json"), expect="none")

    second = generation_project(tmp_path, "gen2", ["001-deploy", "002-status", "003-report", "004-audit"], "lineage-gen2.json")
    check = run_export(sdd_export, second, "check").out
    assert (check["lineage"], check["generation"]) == ("present", 2)
    assert [s["in_lineage"] for s in check["specs"]] == [True, True, True, False]
    result = write_ok(sdd_export, second, fixture("gen2-draft.json"), expect="none")
    assert result.out["counts"]["new"] == 5  # report, report-diff, audit, audit-log, spec-first

    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")
    assert run_export(sdd_export, third, "check").out["generation"] == 3
    write_ok(sdd_export, third, fixture("gen3-draft.json"), expect="none")

    final = json.loads(read_export(third, "nutrients.json"))
    active = {item["id"]: item for section, _, item, _ in sdd_export.walk_items(final) if section != "discarded"}
    gone = {item["id"]: item for item in final["discarded"]}
    derived = {source for item in active.values() for source in item["derived_from"]}
    for item in fixture("gen1-draft.json")["features"]:
        for entry in item["requirements"]:
            rid = entry["id"]
            if rid in active:
                assert active[rid]["origin"] == 1, rid
            elif rid in gone:
                assert gone[rid]["origin"] == 1 and gone[rid]["discarded_in"] >= 2, rid
            else:
                assert rid in derived, rid
    assert active["deploy-no-overwrite"]["origin"] == 1
    assert gone["deploy-symlink"]["discarded_in"] == 2
    assert "status-list" in derived


def test_three_generations_refuse_a_broken_link(sdd_export, tmp_path):
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")
    data = fixture("gen3-draft.json")
    data["features"][0]["requirements"][0]["origin"] = 3
    data["discarded"] = [entry for entry in data["discarded"] if entry["id"] != "deploy-symlink"]

    result = validate(sdd_export, third, data)

    assert {"origin-changed", "discard-lost"} <= set(checks(result))


def gen3_requirement(item_id: str, derived_from: list[str] | None = None) -> dict:
    return {"id": item_id, "origin": 3, "kind": "functional", "text": f"第 3 代的需求 {item_id}。", "revised": [],
            "derived_from": derived_from or [], "source": "spec", "status": "confirmed",
            "evidence": ["specs/002-overview/spec.md"]}


def test_rule_9_refuses_an_id_merged_away_in_an_earlier_generation(sdd_export, tmp_path):
    """T057 (a): status-list was merged into overview-list by the rebuild; it lives on only in derived_from."""
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")
    data = fixture("gen3-draft.json")
    data["features"][1]["requirements"].append(gen3_requirement("status-list"))

    errors = rule_errors(sdd_export, third, data, "id-reused")

    assert [e["path"] for e in errors] == ["features[1].requirements[1].id"]


def test_rule_9_refuses_an_id_merged_away_earlier_in_this_generation(sdd_export, tmp_path, fixed_day):
    """T057 (b): x was added and then merged into y by earlier exports of this generation; it is not free again."""
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")
    first = fixture("gen3-draft.json")
    first["features"][1]["requirements"].append(gen3_requirement("extra-x"))
    state = write_ok(sdd_export, third, first, expect="none").out["state"]
    merged = fixture("gen3-draft.json")
    merged["features"][1]["requirements"].append(gen3_requirement("extra-y", ["extra-x"]))
    write_ok(sdd_export, third, merged, expect=state)

    again = copy.deepcopy(merged)
    again["features"][1]["requirements"].append(gen3_requirement("extra-x"))
    errors = rule_errors(sdd_export, third, again, "id-reused")

    assert [e["path"] for e in errors] == ["features[1].requirements[2].id"]
    assert validate(sdd_export, third, merged).code == 0  # exporting the same nutrients again is still fine


def test_rule_9_keeps_an_item_of_this_generation_that_another_item_derives_from(sdd_export, tmp_path, fixed_day):
    """T057 (c): an item still active in the existing nutrients is that same item, even if another one derives from it."""
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")
    first = fixture("gen3-draft.json")
    first["features"][1]["requirements"].append(gen3_requirement("part-a"))
    state = write_ok(sdd_export, third, first, expect="none").out["state"]
    data = copy.deepcopy(first)
    data["features"][1]["requirements"].append(gen3_requirement("part-b", ["part-a"]))
    write_ok(sdd_export, third, data, expect=state)

    assert validate(sdd_export, third, data).code == 0


def test_rule_9_a_merged_item_splits_back_under_new_ids(sdd_export, tmp_path):
    """T057 (d): overview-list cannot be split back into status-list; a new id derived from it can."""
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")
    reused = fixture("gen3-draft.json")
    reused["features"][1]["requirements"].append(gen3_requirement("status-list", ["overview-list"]))
    fresh = fixture("gen3-draft.json")
    fresh["features"][1]["requirements"].append(gen3_requirement("status-list-again", ["overview-list"]))

    assert [e["path"] for e in rule_errors(sdd_export, third, reused, "id-reused")] == ["features[1].requirements[1].id"]
    assert validate(sdd_export, third, fresh).code == 0


def test_rule_9_still_accepts_the_three_generation_fixtures(sdd_export, tmp_path):
    """T057 (c): keeping the items the rebuild created (overview, overview-list) is not a reuse."""
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")

    assert validate(sdd_export, third, fixture("gen3-draft.json")).code == 0


def test_an_item_the_rebuild_created_is_discarded_not_deleted(sdd_export, tmp_path):
    """T058: an item of the lineage whose origin equals this generation is still the lineage's item."""
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview"], "lineage-gen3.json")
    data = fixture("gen3-draft.json")
    data["features"] = [feature for feature in data["features"] if feature["id"] != "overview"]

    deleted = validate(sdd_export, third, data)
    assert deleted.code == 1 and "lineage-item-missing" in checks(deleted), deleted.out

    for item_id, kind in (("overview", "feature"), ("overview-list", "requirement")):
        data["discarded"].append({"id": item_id, "kind": kind, "origin": 3, "discarded_in": 3, "text": "重建時建立的項目。",
                                  "reason": "維護者決定捨棄"})
    recorded = validate(sdd_export, third, data)
    assert recorded.code == 0, recorded.out


def test_lineage_only_values_are_not_draft_values(sdd_export, tmp_path):
    """T058: the lineage's `source` "rebuild" is refused; its `spec` is the old project's path."""
    third = generation_project(tmp_path, "gen3", ["001-deploy", "002-overview", "003-report"], "lineage-gen3.json")
    lineage = fixture("lineage-gen3.json")
    overview = next(feature for feature in lineage["features"] if feature["id"] == "overview")
    assert overview["spec_dir"] == "specs/002-overview" and overview["spec"] == "specs/003-report/spec.md"

    data = fixture("gen3-draft.json")
    data["features"][1]["source"] = "rebuild"
    assert "field" in checks(validate(sdd_export, third, data))

    data = fixture("gen3-draft.json")
    data["features"][1]["spec"] = overview["spec"]
    # validate only checks that the file exists, so a copied spec points the feature at another feature unnoticed:
    # SKILL.md has to say where the spec comes from.
    assert validate(sdd_export, third, data).code == 0


# ============================================================== re-export


def test_second_write_replaces_the_same_file(sdd_export, tmp_path):
    root = project(tmp_path)
    first = write_ok(sdd_export, root, draft())
    write_ok(sdd_export, root, draft(project="renamed"), expect=first.out["state"])

    assert sorted(p.name for p in (root / ".sdd-export").iterdir()) == [".gitattributes", "README.md", "nutrients.json"]
    assert json.loads(read_export(root, "nutrients.json"))["project"] == "renamed"
    assert run_export(sdd_export, root, "check").out["existing"]["project"] == "renamed"


def test_hand_edit_shows_in_check_and_diff(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    edit_nutrients(root, lambda d: d["features"][0]["requirements"][0].update(text="維護者改過的文字。"))

    out = run_export(sdd_export, root, "check").out
    assert (out["nutrients"], out["view"]) == ("edited", "stale")
    diff = validate(sdd_export, root, draft()).out["diff"]
    assert diff["changed"] == [{"section": "requirements", "id": "deploy-one", "fields": [
        {"field": "text", "from": "維護者改過的文字。", "to": "需求 deploy-one 的可驗收行為。"}]}]


def test_broken_nutrients_stop_and_recover(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    path = root / ".sdd-export" / "nutrients.json"
    good = path.read_bytes()
    path.write_bytes(b"{ not json")
    assert run_export(sdd_export, root, "check").out["reason"] == "nutrients-unreadable"

    path.write_bytes(good)
    assert run_export(sdd_export, root, "check").code == 0


def test_hand_edited_readme_is_regenerated(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    readme = root / ".sdd-export" / "README.md"
    readme.write_text(readme.read_text("utf-8") + "\n維護者的筆記\n", "utf-8")
    check = run_export(sdd_export, root, "check").out
    assert check["view"] == "edited"

    write_ok(sdd_export, root, draft(), expect=check["state"])

    assert "維護者的筆記" not in readme.read_text("utf-8")
    assert run_export(sdd_export, root, "check").out["view"] == "current"


def test_missing_readme(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    (root / ".sdd-export" / "README.md").unlink()

    out = run_export(sdd_export, root, "check").out
    assert (out["view"], out["nutrients"]) == ("missing", "unknown")


def test_old_state_is_refused(sdd_export, tmp_path):
    root = project(tmp_path)
    first = write_ok(sdd_export, root, draft())
    edit_nutrients(root, lambda d: d.update(project="by-hand"))
    before = tree_snapshot(root)

    result = run_export(sdd_export, root, "write", "--expect", first.out["state"], stdin=dump(draft()))

    assert result.out["reason"] == "changed"
    assert tree_snapshot(root) == before


def test_export_in_two_batches(sdd_export, tmp_path):
    root = project(tmp_path, files={"api/routes.py": "r\n", "web/app.js": "a\n"})
    first = draft(scope={"coverage": "partial", "included": ["api"]},
                  features=[feature("api", requirements=[requirement("api-one", evidence=["api/routes.py"])])])
    written = write_ok(sdd_export, root, first)
    second = copy.deepcopy(first)
    second["scope"] = {"coverage": "full", "included": []}
    second["features"].append(feature("web", requirements=[requirement("web-one", evidence=["web/app.js"])]))

    diff = validate(sdd_export, root, second).out["diff"]

    assert diff["scope"] == {"from": {"coverage": "partial", "included": ["api"]}, "to": {"coverage": "full", "included": []}}
    assert [(a["section"], a["id"]) for a in diff["added"]] == [("features", "web"), ("requirements", "web-one")]
    assert diff["removed"] == [] and diff["changed"] == [] and diff["order_changed"] is False
    write_ok(sdd_export, root, second, expect=written.out["state"])


def test_reordered_features(sdd_export, tmp_path):
    root = project(tmp_path)
    data = draft(features=[feature("a"), feature("b", requirements=[requirement("b-one")])])
    write_ok(sdd_export, root, data)
    data["features"].reverse()

    assert validate(sdd_export, root, data).out["diff"]["order_changed"] is True


def test_unchanged_export_has_an_empty_diff(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, full_draft())
    diff = validate(sdd_export, root, full_draft()).out["diff"]

    assert (diff["added"], diff["removed"], diff["changed"], diff["generation"], diff["scope"]) == ([], [], [], None, None)


def rebuilt_lineage() -> dict:
    """lineage_record() plus a feature the rebuild itself added: origin 2, the lineage's own generation."""
    record = lineage_record()
    record["features"].append({
        "id": "report", "origin": 2, "title": "差異報告", "summary": "維護者可以看到差異。", "revised": [],
        "derived_from": [], "source": "rebuild", "spec_dir": "specs/002-report", "spec": None, "depends_on": ["deploy"],
        "requirements": [{"id": "report-diff", "origin": 2, "kind": "functional", "text": "列出差異。", "revised": [],
                          "derived_from": [], "source": "rebuild"}],
    })
    return record


def report_feature(**extra) -> dict:
    item = feature("report", origin=2, source="spec", spec="specs/002-report/spec.md", depends_on=["deploy"],
                   title="差異報告", summary="維護者可以看到差異。",
                   requirements=[requirement("report-diff", origin=2, text="列出差異。", source="spec",
                                             evidence=["specs/002-report/spec.md"])])
    item.update(extra)
    return item


def test_rule_9_items_the_rebuild_created_are_kept_not_reused(sdd_export, tmp_path):
    root = lineage_project(tmp_path, rebuilt_lineage(), specs={"001-deploy": SPEC_TEXT, "002-report": SPEC_TEXT})
    data = gen2_draft()
    data["features"].append(report_feature())
    result = validate(sdd_export, root, data)

    assert result.code == 0, result.out["errors"]
    assert result.out["counts"]["new"] == 2


@pytest.mark.parametrize("case", ["discarded", "earlier-generation", "other-kind"])
def test_rule_9_real_reuse_is_refused(sdd_export, tmp_path, case):
    root = lineage_project(tmp_path, rebuilt_lineage(), specs={"001-deploy": SPEC_TEXT, "002-report": SPEC_TEXT})
    data = gen2_draft()
    data["features"].append(report_feature())
    if case == "discarded":
        data["principles"] = [principle("deploy-symlink", origin=2)]
        path = "principles[0].id"
    elif case == "earlier-generation":
        # deploy-one is a generation-1 requirement of the lineage; a new item may not take its id
        data["features"][0]["requirements"] = [requirement("deploy-one", origin=2, source="spec",
                                                           evidence=["specs/001-deploy/spec.md"])]
        path = "features[0].requirements[0].id"
    else:
        # report is a feature of the lineage; a new lesson may not take its id
        data["features"] = data["features"][:1]
        data["lessons"].append(lesson("report", origin=2))
        data["discarded"].append(discarded("report-diff", kind="requirement", origin=2, discarded_in=2))
        path = "lessons[1].id"

    errors = rule_errors(sdd_export, root, data, "id-reused")

    assert [e["path"] for e in errors] == [path]


def test_rule_5_items_created_in_this_generation_may_change(sdd_export, tmp_path):
    root = lineage_project(tmp_path, rebuilt_lineage(), specs={"001-deploy": SPEC_TEXT, "002-report": SPEC_TEXT})
    changed = gen2_draft()
    changed["features"].append(report_feature(summary="重建後改過的摘要。"))
    changed["features"][1]["requirements"][0]["text"] = "重建後改過的需求。"

    assert validate(sdd_export, root, changed).code == 0


def test_rule_5_inherited_items_still_need_the_mark(sdd_export, tmp_path):
    root = lineage_project(tmp_path, rebuilt_lineage(), specs={"001-deploy": SPEC_TEXT, "002-report": SPEC_TEXT})
    data = gen2_draft()
    data["features"].append(report_feature())
    data["features"][0]["summary"] = "改過的繼承摘要。"

    assert [e["path"] for e in rule_errors(sdd_export, root, data, "revision-unmarked")] == ["features[0].revised"]


def test_rule_5_items_created_in_this_generation_cannot_mark_it(sdd_export, tmp_path):
    root = lineage_project(tmp_path, rebuilt_lineage(), specs={"001-deploy": SPEC_TEXT, "002-report": SPEC_TEXT})
    data = gen2_draft()
    data["features"].append(report_feature(summary="重建後改過的摘要。", revised=[2]))

    assert [e["path"] for e in rule_errors(sdd_export, root, data, "range")] == ["features[1].revised"]


# ============================================ contract locks for 007 sdd-rebuild

DATA_MODEL = REPO_ROOT / "specs" / "006-sdd-export" / "data-model.md"


def example_project(tmp_path: Path, name: str = "my-tool") -> Path:
    """The project the data-model example presupposes: a generation-2 project with spec 001 and a constitution."""
    return make_old_project(tmp_path, name, files={
        "specs/001-deploy/spec.md": SPEC_TEXT,
        ".specify/memory/constitution.md": "# Constitution\n",
        ".sdd-rebuild/lineage.json": (FIXTURES / "lineage-example.json").read_bytes(),
    })


def test_fixtures_have_no_carriage_returns():
    for path in FIXTURES.iterdir():
        assert b"\r" not in path.read_bytes(), path.name


def test_written_bytes_equal_the_fixtures(sdd_export, tmp_path, fixed_day):
    """Both platforms run this test, so both write the very same bytes (FR-019, SC-007)."""
    root = example_project(tmp_path)
    draft_text = (FIXTURES / "draft.json").read_bytes().decode("utf-8")
    write_ok(sdd_export, root, json.loads(draft_text), expect="none")

    assert read_export(root, "nutrients.json") == (FIXTURES / "nutrients.json").read_bytes()
    assert read_export(root, "README.md") == (FIXTURES / "README.md").read_bytes()
    assert read_export(root, ".gitattributes") == (FIXTURES / "gitattributes").read_bytes()
    assert read_export(root, ".gitattributes") == GITATTRIBUTES.encode("utf-8")


def test_readme_fixture_marker_holds_both_hashes():
    readme = (FIXTURES / "README.md").read_bytes()
    first, rest = readme.split(b"\n", 1)
    match = MARKER.match(first.decode("utf-8"))

    assert match
    assert match.group(1) == hashlib.sha256((FIXTURES / "nutrients.json").read_bytes()).hexdigest()
    assert match.group(2) == hashlib.sha256(rest).hexdigest()


def test_nutrients_fixture_is_schema_1_in_key_order():
    data = json.loads((FIXTURES / "nutrients.json").read_bytes().decode("utf-8"))

    assert (data["tool"], data["schema"]) == ("sdd-export", 1)
    assert list(data) == ["tool", "schema", "generation", "project", "exported_at", "language", "scope", "principles",
                          "features", "lessons", "discarded"]


def test_newer_nutrients_are_not_read(sdd_export, tmp_path):
    root = project(tmp_path)
    (root / ".sdd-export").mkdir()
    newer = json.loads((FIXTURES / "nutrients.json").read_bytes())
    newer["schema"] = 2
    (root / ".sdd-export" / "nutrients.json").write_text(json.dumps(newer, ensure_ascii=False), "utf-8")

    result = run_export(sdd_export, root, "check")
    assert (result.code, result.out["reason"], result.out["existing"]) == (3, "nutrients-newer", None)


def example_block(title: str) -> dict:
    """The JSON block under a heading of data-model.md; fails (never skips) when it cannot be found."""
    content = DATA_MODEL.read_bytes().decode("utf-8")
    assert f"### {title}" in content, f"data-model.md has no '### {title}'"
    after = content[content.index(f"### {title}"):]
    start = after.index("```json\n") + len("```json\n")
    return json.loads(after[start:after.index("```", start)])


def json_blocks() -> list[str]:
    content = DATA_MODEL.read_bytes().decode("utf-8")
    return [block.split("```", 1)[0] for block in content.split("```json\n")[1:]]


def test_the_data_model_example_passes_validate_and_write(sdd_export, tmp_path, fixed_day):
    example = example_block("最小範例")
    root = example_project(tmp_path)
    data = {k: v for k, v in example.items() if k not in ("tool", "schema", "exported_at")}

    result = validate(sdd_export, root, data)
    assert result.code == 0, result.out["errors"]
    write_ok(sdd_export, root, data, expect="none")

    written = json.loads(read_export(root, "nutrients.json"))
    assert {k: v for k, v in written.items() if k != "exported_at"} == {k: v for k, v in example.items() if k != "exported_at"}


def test_the_example_matches_the_fixture_lineage():
    example = example_block("最小範例")
    lineage = json.loads((FIXTURES / "lineage-example.json").read_bytes())

    assert example["generation"] == lineage["generation"]
    lineage_ids = {item["id"] for section in ("principles", "features", "lessons") for item in lineage[section]}
    assert {"deploy", "cross-platform", "atomic-write"} <= lineage_ids
    assert [item["id"] for item in lineage["discarded"]] == ["deploy-symlink"]


def test_every_complete_json_example_of_the_data_model_is_checked(sdd_export):
    """There is one complete JSON example today; a new one must be added to the tests above."""
    blocks = json_blocks()
    complete = [block for block in blocks if '"tool": "sdd-export"' in block or '"tool": "sdd-rebuild"' in block]

    assert len(complete) == 1, "a new complete example in data-model.md needs its own validate test"
    assert json.loads(complete[0]) == example_block("最小範例")


# ----------------------------------------------------------- line endings


def test_crlf_copies_are_read_and_not_taken_for_edits(sdd_export, tmp_path, fixed_day):
    root = example_project(tmp_path)
    write_ok(sdd_export, root, json.loads((FIXTURES / "draft.json").read_bytes()), expect="none")
    lf = run_export(sdd_export, root, "check").out
    for path in [root / ".sdd-export" / name for name in ("nutrients.json", "README.md", ".gitattributes")] + \
            [root / ".sdd-rebuild" / "lineage.json"]:
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    crlf = run_export(sdd_export, root, "check")

    assert crlf.code == 0, crlf.out
    out = crlf.out
    assert (out["export_dir"], out["nutrients"], out["view"], out["gitattributes"], out["lineage"]) == \
        ("ours", "unchanged", "current", "ok", "present")
    assert out["state"] == lf["state"]
    assert out["existing"] == lf["existing"]


@needs_git
def test_gitattributes_keeps_lf_through_an_autocrlf_clone(sdd_export, tmp_path):
    source = project(tmp_path, "source", git=True, files={"notes.txt": "one\ntwo\n"})
    write_ok(sdd_export, source, draft())
    git_run(source, "add", "-A")
    git_run(source, "commit", "--quiet", "-m", "nutrients")
    clone = tmp_path / "clone"
    subprocess.run(["git", "-c", "core.autocrlf=true", "clone", "--quiet", str(source), str(clone)], check=True,
                   capture_output=True)
    git_run(clone, "config", "core.autocrlf", "true")
    for rel in (".sdd-export/nutrients.json", ".sdd-export/README.md", "notes.txt"):
        (clone / rel).unlink()
    git_run(clone, "checkout", "--", ".")

    for name in ("nutrients.json", "README.md", ".gitattributes"):
        assert b"\r\n" not in (clone / ".sdd-export" / name).read_bytes(), name


# ------------------------------------------- the rules 007 must follow when writing


def source_nutrients() -> dict:
    """Generation-1 nutrients that sdd-rebuild reads; each rule below turns them into a generation-2 lineage."""
    return nutrients_of(draft(
        principles=[principle("p1")],
        features=[
            feature("f1", requirements=[requirement("r1"), requirement("r2")]),
            feature("f2", requirements=[requirement("r3"), requirement("r4", status="pending", evidence=[])]),
        ],
        lessons=[lesson("l1")],
        discarded=[discarded("d0", kind="doubt")],
    ))


def to_lineage(nutrients: dict) -> dict:
    """The lineage 007 writes when it keeps everything as it is (the first row of the table)."""
    def strip(item):
        return {k: v for k, v in item.items() if k not in ("status", "evidence")}

    features = []
    for number, item in enumerate(nutrients["features"], start=1):
        entry = {}
        for key, value in strip(item).items():
            if key == "requirements":
                continue
            entry[key] = value
            if key == "source":
                entry["spec_dir"] = f"specs/{number:03d}-{item['id']}"
        entry["requirements"] = [strip(r) for r in item["requirements"]]
        features.append(entry)
    return {
        "tool": "sdd-rebuild", "schema": 1, "generation": nutrients["generation"] + 1, "rebuilt_at": "2026-11-21",
        "source": {"project": nutrients["project"], "generation": nutrients["generation"], "nutrients_schema": 1},
        "principles": [strip(p) for p in nutrients["principles"]], "features": features,
        "lessons": [strip(l) for l in nutrients["lessons"]], "discarded": copy.deepcopy(nutrients["discarded"]),
    }


def draft_from_lineage(lineage: dict) -> dict:
    """The next export of the rebuilt project when nothing changed since the rebuild."""
    def add(item, source=None):
        item = copy.deepcopy(item)
        if source and item.get("source") == "rebuild":
            item["source"] = source
        item["status"] = "confirmed"
        item["evidence"] = [".sdd-rebuild/lineage.json"]
        return item

    features = []
    for item in lineage["features"]:
        entry = {k: v for k, v in item.items() if k not in ("spec_dir", "requirements")}
        entry["source"] = "spec"
        entry["spec"] = item["spec_dir"] + "/spec.md"
        entry["requirements"] = [add(r, "spec") for r in item["requirements"]]
        features.append(entry)
    return {
        "generation": lineage["generation"], "project": lineage["source"]["project"], "language": "zh-Hant",
        "scope": {"coverage": "full", "included": []},
        "principles": [add(p, "constitution") for p in lineage["principles"]], "features": features,
        "lessons": [add(l) for l in lineage["lessons"]], "discarded": copy.deepcopy(lineage["discarded"]),
    }


def rebuilt_project(tmp_path: Path, lineage: dict) -> Path:
    files = {f"{item['spec_dir']}/spec.md": SPEC_TEXT for item in lineage["features"] if isinstance(item, dict)}
    files[".sdd-rebuild/lineage.json"] = json.dumps(lineage, ensure_ascii=False, indent=2)
    return make_old_project(tmp_path, "rebuilt", files=files)


def lineage_items(lineage: dict) -> dict:
    return {item["id"]: item for section in ("principles", "features", "lessons") for item in lineage[section]} | \
        {r["id"]: r for f in lineage["features"] for r in f["requirements"]}


def row_keep(lineage):
    pass


def row_modify(lineage):
    r1 = lineage_items(lineage)["r1"]
    r1["text"] = "重建時修改過的需求。"
    r1["revised"] = [2]


def row_merge(lineage):
    f1 = lineage["features"][0]
    f1["requirements"] = [{"id": "r12", "origin": 2, "kind": "functional", "text": "合併後的需求。", "revised": [],
                           "derived_from": ["r1", "r2"], "source": "rebuild"}]


def row_split(lineage):
    f2 = lineage["features"][1]
    r3 = f2["requirements"][0]
    f2["requirements"] = [
        {**r3, "id": "r3a", "origin": 2, "text": "拆分後之一。", "revised": [], "derived_from": ["r3"]},
        {**r3, "id": "r3b", "origin": 2, "text": "拆分後之二。", "revised": [], "derived_from": ["r3"]},
        f2["requirements"][1],
    ]


def row_rebuild_new(lineage):
    lineage["features"].append({
        "id": "f3", "origin": 2, "title": "重建時新增", "summary": "重建時新增的功能。", "revised": [], "derived_from": [],
        "source": "rebuild", "spec_dir": "specs/003-f3", "spec": None, "depends_on": ["f1"],
        "requirements": [{"id": "r5", "origin": 2, "kind": "functional", "text": "新需求。", "revised": [],
                          "derived_from": [], "source": "rebuild"}],
    })


def row_discard(lineage):
    f1 = lineage["features"][0]
    f1["requirements"] = [r for r in f1["requirements"] if r["id"] != "r2"]
    lineage["discarded"].append({"id": "r2", "kind": "requirement", "origin": 1, "discarded_in": 2,
                                 "text": "需求 r2。", "reason": "維護者決定捨棄"})


def row_source_discarded(lineage):
    assert [item["id"] for item in lineage["discarded"]] == ["d0"]


def row_pending_decided(lineage):
    # r4 was pending in the source nutrients; the maintainer kept it during the rebuild, so it has no status here
    assert "status" not in lineage_items(lineage)["r4"]


ROWS = {
    "keep": row_keep, "modify": row_modify, "merge": row_merge, "split": row_split, "rebuild-new": row_rebuild_new,
    "discard": row_discard, "source-discarded": row_source_discarded, "pending-decided": row_pending_decided,
}


def broken_draft(row: str, data: dict) -> str:
    """Break the next export the way that row could be broken; returns the check that must refuse it."""
    items = {item["id"]: item for section, _, item, _ in __import__("sdd_export").walk_items(data) if section != "discarded"}
    if row == "keep":
        items["l1"]["origin"] = 2
        return "origin-changed"
    if row == "modify":
        items["r1"]["text"] = "這一代又改過，但沒有記下。"
        items["r1"]["revised"] = []
        return "revision-unmarked"
    if row == "merge":
        data["features"][0]["requirements"][0]["derived_from"] = ["r1", "r9"]
        return "derived-unknown"
    if row == "split":
        data["features"][1]["requirements"][1]["id"] = "d0"
        return "id-reused"
    if row == "rebuild-new":
        items["f3"]["origin"] = 1
        return "origin-changed"
    if row == "discard":
        data["discarded"] = [entry for entry in data["discarded"] if entry["id"] != "r2"]
        return "discard-lost"
    if row == "source-discarded":
        data["discarded"][0]["reason"] = "改寫了前代的理由"
        return "discard-lost"
    data["features"][1]["requirements"] = [r for r in data["features"][1]["requirements"] if r["id"] != "r4"]
    return "lineage-item-missing"


@pytest.mark.parametrize("row", sorted(ROWS))
def test_007_writing_rules_are_accepted(sdd_export, tmp_path, row):
    lineage = to_lineage(source_nutrients())
    ROWS[row](lineage)
    root = rebuilt_project(tmp_path, lineage)

    check = run_export(sdd_export, root, "check")
    assert (check.code, check.out["lineage"], check.out["generation"]) == (0, "present", 2), check.out
    result = validate(sdd_export, root, draft_from_lineage(lineage))
    assert result.code == 0, result.out["errors"]


@pytest.mark.parametrize("row", sorted(ROWS))
def test_007_writing_rules_refuse_a_broken_next_export(sdd_export, tmp_path, row):
    lineage = to_lineage(source_nutrients())
    ROWS[row](lineage)
    root = rebuilt_project(tmp_path, lineage)
    data = draft_from_lineage(lineage)
    expected = broken_draft(row, data)

    assert expected in checks(validate(sdd_export, root, data))


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda l: lineage_items(l)["r4"].update(status="pending"), "lineage-invalid"),
        (lambda l: l.update(generation=3), "lineage-invalid"),
        (lambda l: lineage_items(l)["r1"].update(origin=2, revised=[2]), "lineage-invalid"),
        (lambda l: l.update(schema=2), "lineage-newer"),
    ],
)
def test_lineages_that_break_the_writing_rules_are_refused(sdd_export, tmp_path, change, reason):
    lineage = to_lineage(source_nutrients())
    change(lineage)
    root = rebuilt_project(tmp_path, lineage)

    result = run_export(sdd_export, root, "check")

    assert (result.code, result.out["reason"]) == (3, reason)


# ======================================== secrets in the existing nutrients and lineage

# A made-up token in the shape of a GitHub token; no real credential.
FAKE_TOKEN = "ghp_" + "Zq8FakeTok" * 3


def leaks(result) -> bool:
    return FAKE_TOKEN in result.raw.decode("utf-8") or FAKE_TOKEN in result.err


def set_lesson_text(data, value):
    data["lessons"][0]["text"] = value


def add_top_key(data, value):
    data[f"https://u:{FAKE_TOKEN}@h.example.com"] = "x"


def add_item_key(data, value):
    data["lessons"][0][f"{FAKE_TOKEN}.x"] = "x"


SECRET_EDITS = [
    (set_lesson_text, f"password={FAKE_TOKEN}", "lessons[0].text", "secret"),
    (set_lesson_text, f"前文\n{FAKE_TOKEN}\n後文", "lessons[0].text", "secret"),
    (lambda d, v: d["features"][0]["requirements"][0].update(text=f"「{v}」"), FAKE_TOKEN,
     "features[0].requirements[0].text", "secret"),
    (lambda d, v: d["features"][0]["requirements"][0]["evidence"].append(v), FAKE_TOKEN,
     "features[0].requirements[0].evidence[1]", "secret"),
    (lambda d, v: d.update(project=v), FAKE_TOKEN, "project", "secret"),
    (add_top_key, None, "(top level)", "secret"),
    (add_item_key, None, "lessons[0]", "secret"),
]


def edited_nutrients(sdd_export, tmp_path, change, value) -> Path:
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    path = root / ".sdd-export" / "nutrients.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data, value)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("change, value, path, check", SECRET_EDITS)
def test_check_refuses_existing_nutrients_that_hold_a_secret(sdd_export, tmp_path, change, value, path, check):
    root = edited_nutrients(sdd_export, tmp_path, change, value)
    result = run_export(sdd_export, root, "check")

    assert result.code == 3
    assert result.out["reason"] == "nutrients-invalid"
    assert result.out["export_dir"] == "invalid"
    assert result.out["existing"] is None
    assert {"check": check, "path": path} in [{k: e[k] for k in ("check", "path")} for e in result.out["errors"]]
    assert not leaks(result)


@pytest.mark.parametrize("change, value, path, check", SECRET_EDITS)
def test_every_command_hides_a_secret_in_the_existing_nutrients(sdd_export, tmp_path, change, value, path, check):
    root = edited_nutrients(sdd_export, tmp_path, change, value)
    state = run_export(sdd_export, root, "check").out["state"]
    results = [
        run_export(sdd_export, root, "files"),
        validate(sdd_export, root, draft()),
        run_export(sdd_export, root, "write", "--expect", state, stdin=dump(draft())),
    ]

    for result in results:
        assert (result.code, result.out["reason"]) == (3, "nutrients-invalid")
        assert not leaks(result)
    assert FAKE_TOKEN not in (root / ".sdd-export" / "README.md").read_text(encoding="utf-8")


def test_a_secret_id_in_the_existing_nutrients_is_not_repeated(sdd_export, tmp_path):
    """An id may be sk- and lowercase letters: a valid id that looks like a key; no detail may repeat it."""
    secret_id = "sk-" + "fakeidvalue" * 3

    def change(data, value):
        data["lessons"].append({**data["lessons"][0], "id": value})
        data["lessons"].append({**data["lessons"][0], "id": value})

    root = edited_nutrients(sdd_export, tmp_path, change, secret_id)
    result = run_export(sdd_export, root, "check")

    assert result.out["reason"] == "nutrients-invalid"
    assert secret_id not in result.raw.decode("utf-8") and secret_id not in result.err


def secret_lineage_project(tmp_path: Path, change) -> Path:
    record = lineage_record()
    change(record)
    return lineage_project(tmp_path, record)


LINEAGE_EDITS = [
    (lambda r: r["lessons"][0].update(text=f"token: {FAKE_TOKEN}"), "lessons[0].text"),
    (lambda r: r["source"].update(project=FAKE_TOKEN), "source.project"),
    (lambda r: r["features"][0].update({f"x.{FAKE_TOKEN}.y": 1}), "features[0]"),
]


@pytest.mark.parametrize("change, path", LINEAGE_EDITS)
def test_check_refuses_a_lineage_that_holds_a_secret(sdd_export, tmp_path, change, path):
    root = secret_lineage_project(tmp_path, change)
    result = run_export(sdd_export, root, "check")

    assert (result.code, result.out["reason"]) == (3, "lineage-invalid")
    assert result.out["lineage"] == "invalid"
    assert result.out["lineage_content"] is None
    assert path in [e["path"] for e in result.out["errors"] if e["check"] == "secret"]
    assert not leaks(result)


@pytest.mark.parametrize("change, path", LINEAGE_EDITS)
def test_every_command_hides_a_secret_in_the_lineage(sdd_export, tmp_path, change, path):
    root = secret_lineage_project(tmp_path, change)
    for result in (run_export(sdd_export, root, "files"), validate(sdd_export, root, gen2_draft()),
                   run_export(sdd_export, root, "write", "--expect", "none", stdin=dump(gen2_draft()))):
        assert (result.code, result.out["reason"]) == (3, "lineage-invalid")
        assert not leaks(result)
    assert not (root / ".sdd-export").exists()


def test_own_nutrients_and_lineage_are_read_back(sdd_export, tmp_path):
    """What sdd-export wrote passed its secret check, so reading it back must not refuse it."""
    root = lineage_project(tmp_path)
    write_ok(sdd_export, root, gen2_draft())
    result = run_export(sdd_export, root, "check")

    assert result.code == 0, result.out
    assert result.out["existing"] is not None and result.out["lineage_content"] == lineage_record()


@pytest.mark.parametrize(
    "name, where",
    [
        (f"{FAKE_TOKEN}.x", "lessons[0]"),
        (f"x.{FAKE_TOKEN}.y", "lessons[0]"),
        (f"https://u:{FAKE_TOKEN}@h.example.com", "lessons[0]"),
        (f"https://u:{FAKE_TOKEN}@h.example.com", "(top level)"),
        (FAKE_TOKEN, "scope"),
    ],
)
def test_a_draft_field_name_that_looks_like_a_secret_is_not_repeated(sdd_export, tmp_path, name, where):
    root = project(tmp_path)
    data = draft()
    target = {"lessons[0]": data["lessons"][0], "(top level)": data, "scope": data["scope"]}[where]
    target[name] = "x"
    result = validate(sdd_export, root, data)

    assert (result.code, result.out["reason"]) == (1, "secret")
    assert where in [e["path"] for e in errors_for(result, "secret")]
    assert not leaks(result)


# ------------------------------------- a hand-edited README.md that looks like it holds a secret (stage 7)


def edited_readme(sdd_export, tmp_path, lines: list[str]) -> Path:
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    path = root / ".sdd-export" / "README.md"
    path.write_bytes(path.read_bytes() + ("\n".join(lines) + "\n").encode("utf-8"))
    return root


def test_check_reports_the_readme_lines_that_look_like_secrets(sdd_export, tmp_path):
    root = edited_readme(sdd_export, tmp_path, ["我加的說明", f"token: {FAKE_TOKEN}", "又一行", FAKE_TOKEN])
    total = (root / ".sdd-export" / "README.md").read_text(encoding="utf-8").count("\n")
    result = run_export(sdd_export, root, "check")

    assert result.code == 0, result.out
    assert result.out["view"] == "edited"
    assert result.out["view_secret_lines"] == [total - 2, total]
    assert not leaks(result)


def test_readme_without_secrets_has_no_lines(sdd_export, tmp_path):
    root = project(tmp_path)
    assert run_export(sdd_export, root, "check").out["view_secret_lines"] == []
    write_ok(sdd_export, root, draft())
    assert run_export(sdd_export, root, "check").out["view_secret_lines"] == []
    edited = edited_readme(sdd_export, tmp_path / "other", ["我加的說明"])
    out = run_export(sdd_export, edited, "check").out
    assert (out["view"], out["view_secret_lines"]) == ("edited", [])


def test_an_undecodable_readme_is_scanned_without_failing(sdd_export, tmp_path):
    root = project(tmp_path)
    write_ok(sdd_export, root, draft())
    path = root / ".sdd-export" / "README.md"
    path.write_bytes(path.read_bytes() + b"\xff\xfe broken\n" + f"password={FAKE_TOKEN}\n".encode("utf-8"))
    result = run_export(sdd_export, root, "check")
    lines = path.read_bytes().count(b"\n")

    assert result.code == 0 and result.out["view_secret_lines"] == [lines]
    assert not leaks(result)


def test_write_regenerates_a_readme_that_held_a_secret(sdd_export, tmp_path):
    """Letting the README edits go: write needs only the state from check, never the README's content."""
    root = edited_readme(sdd_export, tmp_path, [f"token: {FAKE_TOKEN}"])
    state = run_export(sdd_export, root, "check").out["state"]
    result = run_export(sdd_export, root, "write", "--expect", state, stdin=dump(draft()))

    assert result.code == 0, result.out
    assert not leaks(result)
    assert FAKE_TOKEN not in (root / ".sdd-export" / "README.md").read_text(encoding="utf-8")
    out = run_export(sdd_export, root, "check").out
    assert (out["view"], out["view_secret_lines"]) == ("current", [])
