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

    assert keys[:17] == [
        "project", "git", "writable", "export_dir", "nutrients", "view", "gitattributes", "state", "lineage",
        "generation", "existing_generation", "constitution", "specs", "lineage_missing_specs", "inventory",
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
