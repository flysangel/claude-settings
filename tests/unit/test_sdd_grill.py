"""Unit tests for home/skills/sdd-grill/scripts/sdd_grill.py.

The contracts are specs/005-sdd-grill/contracts/cli.md and specs/005-sdd-grill/data-model.md.
Every test runs in a temporary directory; HOME and USERPROFILE point at a temporary directory too.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    CONSTITUTION_TEMPLATE,
    SDD_GRILL_PY,
    WRITTEN_CONSTITUTION,
    git_commit_all,
    git_run,
    run_grill,
    snapshot,
    write_tree,
)

OWN = ".specify/sdd-grill"
PROGRESS = OWN + "/progress.json"
GITIGNORE = OWN + "/.gitignore"
GITIGNORE_CONTENT = "# Created by sdd-grill. Local discussion progress; never committed.\n*\n"
CONFLICT = ".specify/sdd-grill/ holds files sdd-grill did not create; nothing was written"


def sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def minimal_progress(**changes) -> dict:
    progress = {
        "schema": 1,
        "tool": "sdd-grill",
        "requirement": "A small tool that tracks expenses.",
        "language": None,
        "phase": "discussing",
        "stage": "principles",
        "current_feature": None,
        "constitution": {"action": "create", "principles": [], "governance": []},
        "features": [],
        "deferred": [],
        "for_plan": [],
    }
    progress.update(changes)
    return progress


def feature(fid: str, depends_on=(), status="decided", spec_dir=None) -> dict:
    return {
        "id": fid,
        "title": f"Feature {fid}",
        "depends_on": list(depends_on),
        "status": status,
        "decisions": [{"topic": "scope", "decision": f"{fid} does one thing"}],
        "spec_dir": spec_dir,
    }


def confirmed_progress(features: list[dict], action: str = "create", **changes) -> dict:
    principles = [{"title": "Keep it small", "rules": ["Every feature MUST be small."], "rationale": None}]
    progress = minimal_progress(
        language="zh-TW",
        phase="confirmed",
        stage="summary",
        constitution={
            "action": action,
            "principles": principles if action != "keep" else [],
            "governance": [],
        },
        features=features,
    )
    progress.update(changes)
    return progress


def save(module, root: Path, progress) -> object:
    data = progress if isinstance(progress, (str, bytes)) else json.dumps(progress)
    return run_grill(module, root, "save", stdin=data)


def read_progress(root: Path) -> dict:
    return json.loads((root / PROGRESS).read_bytes().decode("utf-8"))


def git_status(root: Path) -> str:
    return git_run(root, "status", "--porcelain", "--untracked-files=all")


# =================================================================== core


@pytest.mark.parametrize("argv", [[], ["nope"], ["check", "extra"], ["save", "--force"], ["clear", "x"]])
def test_usage_errors_exit_1_with_usage_on_stderr(sdd_grill, grill_project, argv):
    root = grill_project()
    before = snapshot(root)

    result = run_grill(sdd_grill, root, *argv)

    assert result.code == 1
    assert "usage" in result.err.lower()
    for command in ("check", "save", "verify", "focus", "clear"):
        assert command in result.err
    assert snapshot(root) == before


def test_loading_the_module_does_nothing(tmp_path, monkeypatch, capsys):
    import importlib.util

    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("sdd_grill_probe", SDD_GRILL_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert list(tmp_path.iterdir()) == []
    assert callable(module.main)


def test_stdout_is_one_json_object_utf8_lf_indent_2(sdd_grill, grill_project):
    root = grill_project()

    result = run_grill(sdd_grill, root, "check")

    assert result.code == 0
    raw = result.raw
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert b"\r" not in raw
    assert raw.decode("utf-8") == json.dumps(result.out, ensure_ascii=False, indent=2) + "\n"
    assert list(result.out) == ["speckit", "missing", "constitution", "numbering", "specs", "progress", "changed", "saved"]


def test_failure_puts_the_same_sentence_in_json_and_stderr(sdd_grill, grill_project):
    root = grill_project(speckit=False)

    result = run_grill(sdd_grill, root, "check")

    assert result.code == 3
    assert result.out["error"]
    assert result.out["error"] in result.err


def test_non_ascii_text_is_written_as_utf8(sdd_grill, grill_project):
    root = grill_project()

    result = save(sdd_grill, root, minimal_progress(requirement="記帳工具"))

    assert result.code == 0
    assert "記帳工具".encode("utf-8") in (root / PROGRESS).read_bytes()


# ----------------------------------------------------------- hashing


def test_content_hash_normalizes_line_endings(sdd_grill):
    lf = sdd_grill.content_hash(b"a\nb\n")

    assert lf == hashlib.sha256(b"a\nb\n").hexdigest()
    assert sdd_grill.content_hash(b"a\r\nb\r\n") == lf
    assert sdd_grill.content_hash(b"a\rb\r") == lf
    assert sdd_grill.content_hash(b"a\nb") != lf
    assert sdd_grill.content_hash(b"a\nc\n") != lf


def test_fingerprint_fields(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"002-b": "B\r\n", "001-a": "A\n"})
    (root / "specs" / "003-no-spec").mkdir()
    write_tree(root, {"specs/notes.txt": "x\n", "specs/004-deep/inner/spec.md": "deep\n"})

    print_ = sdd_grill.fingerprint(root)

    assert list(print_) == ["constitution", "specs", "head"]
    assert print_["constitution"] == sha(WRITTEN_CONSTITUTION)
    assert print_["specs"] == {"specs/001-a/spec.md": sha("A\n"), "specs/002-b/spec.md": sha("B\n")}
    assert list(print_["specs"]) == ["specs/001-a/spec.md", "specs/002-b/spec.md"]
    assert print_["head"] is None  # a git repository without commits


def test_fingerprint_head_is_the_commit(sdd_grill, grill_project):
    root = grill_project()
    git_commit_all(root)

    head = git_run(root, "rev-parse", "HEAD").strip()

    assert sdd_grill.fingerprint(root)["head"] == head


def test_fingerprint_without_git_repository_or_constitution(sdd_grill, grill_project):
    root = grill_project(git=False)

    print_ = sdd_grill.fingerprint(root)

    assert print_ == {"constitution": None, "specs": {}, "head": None}


def test_fingerprint_head_is_null_without_git(sdd_grill, grill_project, monkeypatch):
    root = grill_project()
    git_commit_all(root)
    monkeypatch.setenv("PATH", str(root / "no-such-dir"))

    assert sdd_grill.fingerprint(root)["head"] is None


# ------------------------------------------------------ own folder


def test_own_gitignore_content(sdd_grill, tmp_path):
    folder = tmp_path / "own"

    sdd_grill.ensure_own_folder(folder)

    assert (folder / ".gitignore").read_bytes() == GITIGNORE_CONTENT.encode("utf-8")
    assert sdd_grill.OWN_GITIGNORE == GITIGNORE_CONTENT


def test_own_folder_states(sdd_grill, tmp_path):
    folder = tmp_path / "own"
    assert sdd_grill.own_folder_state(folder) == "absent"

    folder.mkdir()
    assert sdd_grill.own_folder_state(folder) == "ok"

    (folder / ".gitignore").write_bytes(GITIGNORE_CONTENT.replace("\n", "\r\n").encode("utf-8"))
    (folder / "progress.json").write_bytes(b"{}\n")
    assert sdd_grill.own_folder_state(folder) == "ok"


@pytest.mark.parametrize(
    "files",
    [
        {".gitignore": "*\n"},
        {"notes.txt": "mine\n"},
        {"progress.json": "{}\n", "other/file": "x\n"},
        {".gitignore": GITIGNORE_CONTENT, "progress.json.bak": "{}\n"},
    ],
)
def test_own_folder_conflicts(sdd_grill, tmp_path, files):
    folder = tmp_path / "own"
    folder.mkdir()
    write_tree(folder, files)

    assert sdd_grill.own_folder_state(folder) == "conflict"


def test_own_folder_that_is_a_file_is_a_conflict(sdd_grill, tmp_path):
    (tmp_path / "own").write_bytes(b"x")

    assert sdd_grill.own_folder_state(tmp_path / "own") == "conflict"


def test_atomic_write_replaces_and_leaves_no_temporary_file(sdd_grill, tmp_path):
    target = tmp_path / "file.json"
    target.write_bytes(b"old")

    sdd_grill.atomic_write(target, b"new\n")

    assert target.read_bytes() == b"new\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.json"]


def test_atomic_write_failure_keeps_the_old_file(sdd_grill, tmp_path, monkeypatch):
    target = tmp_path / "file.json"
    target.write_bytes(b"old")

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(sdd_grill.os, "replace", broken_replace)
    with pytest.raises(OSError):
        sdd_grill.atomic_write(target, b"new\n")

    assert target.read_bytes() == b"old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.json"]


def test_remove_own_files(sdd_grill, tmp_path):
    folder = tmp_path / "own"
    sdd_grill.ensure_own_folder(folder)
    (folder / "progress.json").write_bytes(b"{}\n")

    assert sdd_grill.remove_own_files(folder) is True
    assert not folder.exists()
    assert sdd_grill.remove_own_files(folder) is False


# ---------------------------------------------------------- secrets


@pytest.mark.parametrize(
    "value",
    [
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "use ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "github_pat_" + "11ABCDEFG0123456789_abcdefghijklmnop",
        "key sk-" + "proj-abcdefghijklmnopqrstuvwx",
        "xoxb-" + "1234567890-abcdefghij",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "postgres://admin:hunter2@db.example.invalid/app",
        "password=hunter2",
        "the db password: hunter2",
        "SECRET=abc",
        "token:abc123",
        "api_key = xyz",
        "API-KEY: xyz",
    ],
)
def test_secret_patterns_are_found_without_echoing_the_value(sdd_grill, value):
    data = {"features": [{"decisions": [{"topic": "access", "decision": value}]}]}

    found = sdd_grill.find_secret(data)

    assert found == "features[0].decisions[0].decision"
    assert "hunter2" not in found


@pytest.mark.parametrize(
    "value",
    [
        "The tool needs an API key to call the service; the maintainer keeps it outside the project.",
        "Users sign in with a password.",
        "A token budget of 1000 per request.",
        "very_long_identifier_name_for_the_expense_tracker_module_v2",
        "https://example.invalid/docs/page",
        "sk-learn is not a token",
        "Secrets are stored in the operating system keychain.",
        "4f9c2a1b8e7d6c5b4a39281706f5e4d3c2b1a09f",
    ],
)
def test_ordinary_text_is_not_a_secret(sdd_grill, value):
    assert sdd_grill.find_secret({"requirement": value, "list": [value]}) is None


def test_secret_path_for_top_level_and_lists(sdd_grill):
    assert sdd_grill.find_secret({"requirement": "password=x"}) == "requirement"
    assert sdd_grill.find_secret({"a": ["ok", "token=x"]}) == "a[1]"
