"""Unit tests for home/skills/sdd-grill/scripts/sdd_grill.py.

The contracts are specs/005-sdd-grill/contracts/cli.md and specs/005-sdd-grill/data-model.md.
Every test runs in a temporary directory; HOME and USERPROFILE point at a temporary directory too.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    folder_sets_for_this_platform,
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


# ================================================================== check

MISSING_SENTENCE = "Spec Kit is not set up in this project; run /sdd-init first."
INCOMPLETE_SENTENCE = (
    "Spec Kit in this project lacks files needed to generate a constitution and specs; it may have changed incompatibly."
)


def test_check_without_specify_folder(sdd_grill, grill_project):
    root = grill_project(speckit=False)

    result = run_grill(sdd_grill, root, "check")

    assert result.code == 3
    assert result.out["speckit"] == "missing"
    assert result.out["missing"] == []
    assert result.out["error"] == MISSING_SENTENCE
    assert result.out["constitution"] == "missing"
    assert result.out["progress"] == "none"
    assert [p.name for p in root.iterdir()] == [".git"]


@pytest.mark.parametrize(
    "omit",
    [
        (".claude/skills/speckit-specify/SKILL.md",),
        (".specify/templates/spec-template.md", ".claude/skills/speckit-constitution/SKILL.md"),
        (".specify/scripts/bash/resolve-template.sh",),
        (".specify/templates/constitution-template.md",),
    ],
)
def test_check_with_incomplete_speckit(sdd_grill, grill_project, omit):
    root = grill_project(omit=omit)
    before = snapshot(root)

    result = run_grill(sdd_grill, root, "check")

    assert result.code == 3
    assert result.out["speckit"] == "incomplete"
    assert result.out["missing"] == sorted(omit)
    assert result.out["error"] == INCOMPLETE_SENTENCE
    assert snapshot(root) == before


def test_check_with_complete_speckit(sdd_grill, grill_project):
    root = grill_project()

    result = run_grill(sdd_grill, root, "check")

    assert result.code == 0
    assert result.out == {
        "speckit": "ok",
        "missing": [],
        "constitution": "missing",
        "numbering": "sequential",
        "specs": [],
        "progress": "none",
        "changed": [],
        "saved": None,
    }


@pytest.mark.parametrize(
    "content, expected",
    [
        (CONSTITUTION_TEMPLATE, "template"),
        (CONSTITUTION_TEMPLATE.replace("\n", "\r\n"), "template"),
        ("# My [PROJECT_NAME]\n\nfilled in elsewhere\n", "template"),
        ("# Demo\n\n### [PRINCIPLE_1_NAME]\n", "template"),
        (WRITTEN_CONSTITUTION, "written"),
    ],
)
def test_check_constitution_state(sdd_grill, grill_project, content, expected):
    root = grill_project(constitution=content)

    assert run_grill(sdd_grill, root, "check").out["constitution"] == expected


def test_check_lists_specs_with_numbers(sdd_grill, grill_project):
    root = grill_project(
        specs={
            "002-b": "b\n",
            "001-a": "a\n",
            "20261120-153000-c": "c\n",
            "notes": "n\n",
            "12-short": "s\n",
            "1000-big": "x\n",
        }
    )
    (root / "specs" / "003-no-spec").mkdir()
    write_tree(root, {"specs/004-deep/inner/spec.md": "deep\n", "specs/loose.md": "x\n"})

    specs = run_grill(sdd_grill, root, "check").out["specs"]

    assert specs == [
        {"dir": "specs/001-a", "number": "001"},
        {"dir": "specs/002-b", "number": "002"},
        {"dir": "specs/1000-big", "number": "1000"},
        {"dir": "specs/12-short", "number": None},
        {"dir": "specs/20261120-153000-c", "number": "20261120-153000"},
        {"dir": "specs/notes", "number": None},
    ]


@pytest.mark.parametrize(
    "options, expected",
    [
        (None, "sequential"),
        ('{"feature_numbering": "timestamp"}', "timestamp"),
        ('{"branch_numbering": "timestamp"}', "timestamp"),
        ('{"feature_numbering": "sequential", "branch_numbering": "timestamp"}', "sequential"),
        ('{"integration": "claude"}', "sequential"),
        ("not json", "sequential"),
        ("[1, 2]", "sequential"),
        ('{"feature_numbering": 3}', "sequential"),
    ],
)
def test_check_numbering(sdd_grill, grill_project, options, expected):
    root = grill_project(init_options=options)

    assert run_grill(sdd_grill, root, "check").out["numbering"] == expected


def test_check_writes_nothing(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-a": "a\n"})
    git_commit_all(root)
    assert save(sdd_grill, root, minimal_progress()).code == 0
    before = snapshot(root, with_mtime=True)

    run_grill(sdd_grill, root, "check")
    run_grill(sdd_grill, root, "check")

    assert snapshot(root, with_mtime=True) == before


# =========================================================== save: discussing


def test_save_minimal_progress(sdd_grill, grill_project):
    root = grill_project()

    result = save(sdd_grill, root, minimal_progress())

    assert result.code == 0
    assert result.out == {"saved": PROGRESS, "phase": "discussing", "baseline": False}
    raw = (root / PROGRESS).read_bytes()
    assert b"\r" not in raw and raw.endswith(b"}\n")
    stored = json.loads(raw.decode("utf-8"))
    assert raw.decode("utf-8") == json.dumps(stored, ensure_ascii=False, indent=2) + "\n"
    assert list(stored) == list(minimal_progress()) + ["saved_at", "fingerprint", "baseline"]
    assert stored["fingerprint"] == sdd_grill.fingerprint(root) | {"specs": {}}
    assert stored["baseline"] is None
    assert len(stored["saved_at"]) == 20 and stored["saved_at"].endswith("Z")
    assert (root / GITIGNORE).read_bytes() == GITIGNORE_CONTENT.encode("utf-8")


def test_save_ignores_the_fields_the_script_writes(sdd_grill, grill_project):
    root = grill_project()
    progress = minimal_progress(saved_at="yesterday", fingerprint={"head": "x"}, baseline={"specs": {}})

    assert save(sdd_grill, root, progress).code == 0

    stored = read_progress(root)
    assert stored["saved_at"] != "yesterday"
    assert stored["fingerprint"]["head"] != "x"
    assert stored["baseline"] is None


def test_saved_progress_stays_out_of_git(sdd_grill, grill_project):
    root = grill_project()
    git_commit_all(root, "spec kit")

    assert save(sdd_grill, root, minimal_progress()).code == 0

    assert git_status(root) == ""
    git_run(root, "add", "-A")
    assert git_status(root) == ""


def test_saving_the_same_input_twice_gives_the_same_content(sdd_grill, grill_project):
    root = grill_project()
    progress = minimal_progress(features=[feature("a", status="pending"), feature("b", ["a"], status="pending")])

    save(sdd_grill, root, progress)
    first = read_progress(root)
    save(sdd_grill, root, progress)
    second = read_progress(root)

    first.pop("saved_at"), second.pop("saved_at")
    assert first == second


def test_save_keeps_a_fixed_key_order(sdd_grill, grill_project):
    root = grill_project()
    progress = minimal_progress(features=[feature("a", status="pending")])
    shuffled = dict(reversed(list(progress.items())))
    shuffled["features"] = [dict(reversed(list(progress["features"][0].items())))]

    save(sdd_grill, root, progress)
    first = (root / PROGRESS).read_bytes()
    save(sdd_grill, root, shuffled)
    second = (root / PROGRESS).read_bytes()

    strip = lambda raw: [l for l in raw.split(b"\n") if b"saved_at" not in l]
    assert strip(first) == strip(second)


def test_save_rejects_input_that_is_not_json(sdd_grill, grill_project):
    root = grill_project()

    result = save(sdd_grill, root, "{not json")

    assert result.code == 1
    assert result.out["error"].startswith("progress is not valid JSON: ")
    assert not (root / OWN).exists()


def _with(path: str, value):
    """A minimal progress (with two features) where the field at path is replaced or removed."""
    progress = minimal_progress(
        stage="feature",
        current_feature="a",
        features=[feature("a", status="discussing"), feature("b", ["a"], status="pending")],
        deferred=[{"item": "export", "reason": "later", "feature": "b"}],
        for_plan=[{"item": "database", "feature": None}],
    )
    target = progress
    keys = re.findall(r"[^.\[\]]+", path)
    for key in keys[:-1]:
        target = target[int(key)] if key.isdigit() else target[key]
    last = keys[-1]
    if value is _REMOVE:
        del target[last]
    elif last.isdigit():
        target[int(last)] = value
    else:
        target[last] = value
    return progress




_REMOVE = object()


@pytest.mark.parametrize(
    "path, value, expected_path",
    [
        ("extra", 1, "extra"),
        ("requirement", _REMOVE, "requirement"),
        ("schema", 2, "schema"),
        ("schema", True, "schema"),
        ("schema", "1", "schema"),
        ("tool", "sdd-rebuild", "tool"),
        ("requirement", "", "requirement"),
        ("requirement", "   ", "requirement"),
        ("requirement", None, "requirement"),
        ("language", "", "language"),
        ("language", 5, "language"),
        ("phase", "done", "phase"),
        ("stage", "plan", "stage"),
        ("current_feature", None, "current_feature"),
        ("current_feature", "zzz", "current_feature"),
        ("constitution.action", "rewrite", "constitution.action"),
        ("constitution.extra", [], "constitution.extra"),
        ("constitution.principles", [{"title": "", "rules": [], "rationale": None}], "constitution.principles[0].title"),
        ("constitution.principles", [{"title": "t", "rules": [""], "rationale": None}], "constitution.principles[0].rules[0]"),
        ("constitution.governance", [3], "constitution.governance[0]"),
        ("features", {}, "features"),
        ("features[1].id", "a", "features[1].id"),
        ("features[1].id", "Bad_Id", "features[1].id"),
        ("features[1].id", "-b", "features[1].id"),
        ("features[0].title", "", "features[0].title"),
        ("features[0].depends_on", ["b"], "features[0].depends_on[0]"),
        ("features[1].depends_on", ["specs/009-none"], "features[1].depends_on[0]"),
        ("features[1].depends_on", ["c"], "features[1].depends_on[0]"),
        ("features[0].status", "done", "features[0].status"),
        ("features[0].decisions", [{"topic": "x"}], "features[0].decisions[0].decision"),
        ("features[0].spec_dir", "specs/001-a", "features[0].spec_dir"),
        ("deferred[0].feature", "zzz", "deferred[0].feature"),
        ("deferred[0].reason", "", "deferred[0].reason"),
        ("for_plan[0].feature", "zzz", "for_plan[0].feature"),
        ("for_plan[0].extra", 1, "for_plan[0].extra"),
    ],
)
def test_save_rejects_invalid_progress(sdd_grill, grill_project, path, value, expected_path):
    root = grill_project()

    result = save(sdd_grill, root, _with(path, value))

    assert result.code == 1, result.out
    assert result.out["error"].startswith(f"progress is invalid at {expected_path}: "), result.out["error"]
    assert not (root / OWN).exists()


def test_save_rejects_a_top_level_that_is_not_an_object(sdd_grill, grill_project):
    root = grill_project()

    result = save(sdd_grill, root, "[1, 2]")

    assert result.code == 1
    assert result.out["error"].startswith("progress is invalid at ")


def test_stage_other_than_feature_needs_no_current_feature(sdd_grill, grill_project):
    root = grill_project()

    result = save(sdd_grill, root, _with("stage", "features"))

    assert result.code == 1
    assert result.out["error"].startswith("progress is invalid at current_feature: ")


def test_depends_on_may_name_an_existing_spec_folder(sdd_grill, grill_project):
    root = grill_project(specs={"003-old": "old\n"})
    (root / "specs" / "004-empty").mkdir()

    ok = save(sdd_grill, root, _with("features[0].depends_on", ["specs/003-old"]))
    empty = save(sdd_grill, root, _with("features[0].depends_on", ["specs/004-empty"]))

    assert ok.code == 0
    assert empty.code == 1 and "features[0].depends_on[0]" in empty.out["error"]


def test_save_rejects_a_secret_and_keeps_the_old_progress(sdd_grill, grill_project):
    root = grill_project()
    assert save(sdd_grill, root, minimal_progress()).code == 0
    before = (root / PROGRESS).read_bytes()

    progress = minimal_progress(features=[feature("a", status="discussing")], stage="feature", current_feature="a")
    progress["features"][0]["decisions"][0]["decision"] = "connect with password=hunter2"
    result = save(sdd_grill, root, progress)

    assert result.code == 1
    assert result.out["error"] == (
        "progress at features[0].decisions[0].decision looks like a secret; "
        "describe what is needed instead of recording the value"
    )
    assert "hunter2" not in result.err and "hunter2" not in result.raw.decode("utf-8")
    assert (root / PROGRESS).read_bytes() == before


def test_save_stops_on_a_folder_conflict(sdd_grill, grill_project):
    root = grill_project()
    write_tree(root, {OWN + "/notes.txt": "mine\n"})
    before = snapshot(root)

    result = save(sdd_grill, root, minimal_progress())

    assert result.code == 1
    assert result.out["error"] == CONFLICT
    assert snapshot(root) == before


def test_save_does_not_need_spec_kit(sdd_grill, grill_project):
    root = grill_project(speckit=False)

    assert save(sdd_grill, root, minimal_progress()).code == 0
    assert (root / PROGRESS).is_file()


def test_save_writes_only_its_own_folder(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-a": "a\n"})
    before = snapshot(root)

    save(sdd_grill, root, minimal_progress())

    after = snapshot(root)
    changed = {k for k in set(before) | set(after) if before.get(k, 0) != after.get(k, 0)}
    assert changed and all(k.startswith(OWN) for k in changed), changed


# =========================================================== save: confirmed


def test_confirmed_requires_summary_decided_and_language(sdd_grill, grill_project):
    root = grill_project()
    cases = [
        (confirmed_progress([feature("a")], stage="feature", current_feature="a"), "stage"),
        (confirmed_progress([feature("a"), feature("b", status="discussing")]), "features[1].status"),
        (confirmed_progress([feature("a")], language=None), "language"),
    ]
    for progress, path in cases:
        result = save(sdd_grill, root, progress)
        assert result.code == 1
        assert result.out["error"].startswith(f"progress is invalid at {path}: "), result.out["error"]
    assert not (root / OWN).exists()


def test_first_confirmed_save_records_the_baseline(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-old": "old\n"})
    assert save(sdd_grill, root, minimal_progress()).code == 0

    result = save(sdd_grill, root, confirmed_progress([feature("a")]))

    assert result.code == 0
    assert result.out == {"saved": PROGRESS, "phase": "confirmed", "baseline": True}
    assert read_progress(root)["baseline"] == {
        "constitution": sha(WRITTEN_CONSTITUTION),
        "specs": {"specs/001-old/spec.md": sha("old\n")},
    }


def test_later_saves_keep_the_baseline(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    save(sdd_grill, root, confirmed_progress([feature("a"), feature("b", ["a"])]))
    baseline = read_progress(root)["baseline"]

    write_tree(root, {".specify/memory/constitution.md": "# Changed\n", "specs/001-a/spec.md": "a\n"})
    progress = confirmed_progress([feature("a", spec_dir="specs/001-a"), feature("b", ["a"])])
    progress["baseline"] = {"constitution": None, "specs": {}}
    result = save(sdd_grill, root, progress)

    assert result.code == 0 and result.out["baseline"] is False
    assert read_progress(root)["baseline"] == baseline
    assert read_progress(root)["fingerprint"]["specs"] == {"specs/001-a/spec.md": sha("a\n")}


@pytest.mark.parametrize(
    "spec_dir",
    ["/abs/specs/001-a", "specs/../001-a", "specs/..", "specs/001-a/inner", "specs\\001-a", "001-a", "specs/", "other/001-a"],
)
def test_spec_dir_must_be_one_folder_under_specs(sdd_grill, grill_project, spec_dir):
    root = grill_project()

    result = save(sdd_grill, root, confirmed_progress([feature("a", spec_dir=spec_dir)]))

    assert result.code == 1
    assert result.out["error"].startswith("progress is invalid at features[0].spec_dir: ")


def test_back_to_discussing_is_refused_once_a_spec_exists(sdd_grill, grill_project):
    root = grill_project()
    save(sdd_grill, root, confirmed_progress([feature("a"), feature("b", ["a"])]))
    save(sdd_grill, root, confirmed_progress([feature("a", spec_dir="specs/001-a"), feature("b", ["a"])]))
    before = (root / PROGRESS).read_bytes()

    back = minimal_progress(stage="summary", features=[feature("a"), feature("b", ["a"])])
    result = save(sdd_grill, root, back)

    assert result.code == 1
    assert result.out["error"] == (
        "specs were already generated from the confirmed summary; it can no longer go back to discussing"
    )
    assert (root / PROGRESS).read_bytes() == before


def test_back_to_discussing_before_any_spec_resets_the_baseline(sdd_grill, grill_project):
    root = grill_project()
    save(sdd_grill, root, confirmed_progress([feature("a")]))

    result = save(sdd_grill, root, minimal_progress(stage="summary", features=[feature("a")]))

    assert result.code == 0 and result.out == {"saved": PROGRESS, "phase": "discussing", "baseline": False}
    assert read_progress(root)["baseline"] is None
    write_tree(root, {"specs/001-new/spec.md": "new\n"})
    again = save(sdd_grill, root, confirmed_progress([feature("a")]))
    assert again.out["baseline"] is True
    assert read_progress(root)["baseline"]["specs"] == {"specs/001-new/spec.md": sha("new\n")}


# ================================================================== verify

NOTHING_TO_VERIFY = "there is no confirmed summary to verify"
MISMATCH = "the generated documents do not match the confirmed summary"


def generated(sdd_grill, root: Path, features: list[dict], dirs: dict[str, str], action="create", constitution=None):
    """Confirm features, then 'generate' the given spec folders and record them as spec_dir."""
    assert save(sdd_grill, root, confirmed_progress(features, action)).code == 0
    if constitution is not None:
        write_tree(root, {".specify/memory/constitution.md": constitution})
    for fid, folder in dirs.items():
        write_tree(root, {f"{folder}/spec.md": f"spec of {fid}\n"})
    done = copy.deepcopy(features)
    for entry in done:
        entry["spec_dir"] = dirs.get(entry["id"])
    assert save(sdd_grill, root, confirmed_progress(done, action)).code == 0
    return done


def failures(result) -> list[str]:
    return [f["check"] for f in result.out["failures"]]


def test_verify_needs_a_confirmed_progress(sdd_grill, grill_project):
    root = grill_project()
    assert run_grill(sdd_grill, root, "verify").out["error"] == NOTHING_TO_VERIFY

    save(sdd_grill, root, minimal_progress())
    result = run_grill(sdd_grill, root, "verify")

    assert result.code == 1 and result.out["error"] == NOTHING_TO_VERIFY


def test_verify_passes_and_lists_the_specs(sdd_grill, grill_project):
    root = grill_project(constitution=CONSTITUTION_TEMPLATE)
    generated(
        sdd_grill,
        root,
        [feature("a"), feature("b", ["a"]), feature("c", ["a", "b"])],
        {"a": "specs/001-a", "b": "specs/002-b", "c": "specs/003-c"},
        constitution=WRITTEN_CONSTITUTION,
    )

    result = run_grill(sdd_grill, root, "verify")

    assert result.code == 0
    assert result.out == {
        "ok": True,
        "failures": [],
        "constitution": "written",
        "specs": [
            {"feature": "a", "dir": "specs/001-a", "depends_on": []},
            {"feature": "b", "dir": "specs/002-b", "depends_on": ["specs/001-a"]},
            {"feature": "c", "dir": "specs/003-c", "depends_on": ["specs/001-a", "specs/002-b"]},
        ],
        "unexpected": [],
    }


def test_verify_keeps_ids_of_features_without_spec_dir(sdd_grill, grill_project):
    root = grill_project()
    generated(sdd_grill, root, [feature("a"), feature("b", ["a"])], {}, constitution=WRITTEN_CONSTITUTION)

    result = run_grill(sdd_grill, root, "verify")

    assert result.code == 1
    assert result.out["error"] == MISMATCH
    assert result.out["specs"][1] == {"feature": "b", "dir": None, "depends_on": ["a"]}
    assert failures(result) == ["spec-missing", "spec-missing"]
    assert "a" in result.out["failures"][0]["detail"]


def test_verify_existing_spec_changed_or_removed(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-old": "old\n", "002-old": "old 2\n"})
    generated(sdd_grill, root, [feature("a")], {"a": "specs/003-a"}, action="keep")
    write_tree(root, {"specs/001-old/spec.md": "edited\n"})
    (root / "specs/002-old/spec.md").unlink()

    result = run_grill(sdd_grill, root, "verify")

    assert failures(result) == ["existing-spec-changed", "existing-spec-changed"]
    details = [f["detail"] for f in result.out["failures"]]
    assert "specs/001-old/spec.md" in details[0] and "specs/002-old/spec.md" in details[1]


def test_verify_existing_spec_with_other_line_endings_is_unchanged(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-old": "old\nline\n"})
    generated(sdd_grill, root, [feature("a")], {"a": "specs/002-a"}, action="keep")
    write_tree(root, {"specs/001-old/spec.md": b"old\r\nline\r\n"})

    assert run_grill(sdd_grill, root, "verify").out["ok"] is True


def test_verify_constitution_kept(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    generated(sdd_grill, root, [feature("a")], {"a": "specs/001-a"}, action="keep")
    assert run_grill(sdd_grill, root, "verify").out["ok"] is True

    write_tree(root, {".specify/memory/constitution.md": WRITTEN_CONSTITUTION + "- More.\n"})
    result = run_grill(sdd_grill, root, "verify")

    assert failures(result) == ["constitution-changed"]
    assert ".specify/memory/constitution.md" in result.out["failures"][0]["detail"]


@pytest.mark.parametrize("start, after", [(None, None), (CONSTITUTION_TEMPLATE, CONSTITUTION_TEMPLATE)])
def test_verify_constitution_create_not_written(sdd_grill, grill_project, start, after):
    root = grill_project(constitution=start)
    generated(sdd_grill, root, [feature("a")], {"a": "specs/001-a"}, action="create", constitution=after)

    result = run_grill(sdd_grill, root, "verify")

    assert failures(result) == ["constitution-not-written"]
    assert result.code == 1


def test_verify_constitution_amend(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    generated(sdd_grill, root, [feature("a")], {"a": "specs/001-a"}, action="amend")
    assert failures(run_grill(sdd_grill, root, "verify")) == ["constitution-not-written"]

    write_tree(root, {".specify/memory/constitution.md": WRITTEN_CONSTITUTION + "- Amended.\n"})
    assert run_grill(sdd_grill, root, "verify").out["ok"] is True


def test_verify_spec_dir_without_spec_md(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    generated(sdd_grill, root, [feature("a")], {"a": "specs/001-a"}, action="keep")
    (root / "specs/001-a/spec.md").unlink()

    result = run_grill(sdd_grill, root, "verify")

    assert failures(result) == ["spec-missing"]
    assert "specs/001-a" in result.out["failures"][0]["detail"]


def test_verify_spec_not_new(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-old": "old\n"})
    generated(
        sdd_grill, root, [feature("a"), feature("b")], {"a": "specs/001-old", "b": "specs/001-old"}, action="keep"
    )

    result = run_grill(sdd_grill, root, "verify")

    assert "spec-not-new" in failures(result)
    assert any("specs/001-old" in f["detail"] for f in result.out["failures"] if f["check"] == "spec-not-new")


def test_verify_duplicate_spec_dirs_are_not_new(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    generated(sdd_grill, root, [feature("a"), feature("b")], {"a": "specs/001-a", "b": "specs/001-a"}, action="keep")

    assert "spec-not-new" in failures(run_grill(sdd_grill, root, "verify"))


def test_verify_order_and_dependency_order(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    generated(
        sdd_grill, root, [feature("a"), feature("b", ["a"])], {"a": "specs/002-a", "b": "specs/001-b"}, action="keep"
    )

    result = run_grill(sdd_grill, root, "verify")

    assert failures(result) == ["order", "dependency-order"]
    assert "specs/001-b" in result.out["failures"][0]["detail"]
    assert "specs/001-b" in result.out["failures"][1]["detail"] and "specs/002-a" in result.out["failures"][1]["detail"]


def test_verify_order_without_a_number(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    generated(sdd_grill, root, [feature("a")], {"a": "specs/a-without-number"}, action="keep")

    result = run_grill(sdd_grill, root, "verify")

    assert failures(result) == ["order"]
    assert "specs/a-without-number" in result.out["failures"][0]["detail"]


def test_verify_order_compares_sequential_numbers_as_integers(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"999-old": "old\n"})
    generated(
        sdd_grill, root, [feature("a"), feature("b", ["a"])], {"a": "specs/1000-a", "b": "specs/1001-b"}, action="keep"
    )

    assert run_grill(sdd_grill, root, "verify").out["ok"] is True


def test_verify_order_compares_timestamps_as_strings(sdd_grill, grill_project):
    root = grill_project(
        constitution=WRITTEN_CONSTITUTION,
        init_options='{"feature_numbering": "timestamp"}',
        specs={"20261101-090000-old": "old\n"},
    )
    generated(
        sdd_grill,
        root,
        [feature("a"), feature("b", ["a"])],
        {"a": "specs/20261120-100000-a", "b": "specs/20261120-100005-b"},
        action="keep",
    )
    assert run_grill(sdd_grill, root, "verify").out["ok"] is True


def test_verify_lists_all_failures_at_once(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-old": "old\n"})
    generated(
        sdd_grill,
        root,
        [feature("a"), feature("b", ["a"]), feature("c")],
        {"a": "specs/003-a", "b": "specs/002-b"},
        action="keep",
    )
    write_tree(root, {"specs/001-old/spec.md": "edited\n", ".specify/memory/constitution.md": "# Other\n"})

    result = run_grill(sdd_grill, root, "verify")

    assert failures(result) == [
        "existing-spec-changed",
        "constitution-changed",
        "spec-missing",
        "order",
        "dependency-order",
    ]


def test_verify_reports_unexpected_folders_without_failing(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-old": "old\n"})
    generated(sdd_grill, root, [feature("a")], {"a": "specs/002-a"}, action="keep")
    write_tree(root, {"specs/003-stray/spec.md": "stray\n", "specs/004-no-spec/notes.md": "x\n"})

    result = run_grill(sdd_grill, root, "verify")

    assert result.code == 0 and result.out["ok"] is True
    assert result.out["unexpected"] == ["specs/003-stray"]


def test_verify_writes_nothing(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    generated(sdd_grill, root, [feature("a")], {"a": "specs/002-a"}, action="keep")
    before = snapshot(root, with_mtime=True)

    run_grill(sdd_grill, root, "verify")
    write_tree(root, {"specs/002-a/spec.md": "x\n"})
    before_failing = snapshot(root, with_mtime=True)
    run_grill(sdd_grill, root, "verify")

    assert snapshot(root, with_mtime=True) == before_failing
    assert set(before) == set(before_failing)


# =================================================================== focus

NOTHING_TO_POINT_AT = "there is no confirmed summary to point at"
FOCUS_MISMATCH = "the generated documents do not match the confirmed summary; .specify/feature.json was not changed"
NOT_REGULAR = ".specify/feature.json is not a regular file; nothing was written"
FEATURE_JSON = ".specify/feature.json"


def feature_json(directory: str) -> bytes:
    return (json.dumps({"feature_directory": directory}, indent=2) + "\n").encode("utf-8")


def two_generated(sdd_grill, root: Path, **options):
    generated(
        sdd_grill,
        root,
        [feature("a"), feature("b", ["a"])],
        {"a": "specs/001-a", "b": "specs/002-b"},
        constitution=WRITTEN_CONSTITUTION,
        **options,
    )


def test_focus_needs_a_confirmed_progress(sdd_grill, grill_project):
    root = grill_project()
    write_tree(root, {FEATURE_JSON: feature_json("specs/002-b")})
    assert run_grill(sdd_grill, root, "focus").out["error"] == NOTHING_TO_POINT_AT

    save(sdd_grill, root, minimal_progress())
    result = run_grill(sdd_grill, root, "focus")

    assert result.code == 1 and result.out["error"] == NOTHING_TO_POINT_AT
    assert (root / FEATURE_JSON).read_bytes() == feature_json("specs/002-b")


def test_focus_does_not_write_when_verify_fails(sdd_grill, grill_project):
    root = grill_project()
    generated(
        sdd_grill,
        root,
        [feature("a"), feature("b", ["a"])],
        {"a": "specs/002-a", "b": "specs/001-b"},
        constitution=WRITTEN_CONSTITUTION,
    )
    original = b'{"feature_directory": "specs/001-b"}'
    write_tree(root, {FEATURE_JSON: original})

    result = run_grill(sdd_grill, root, "focus")

    assert result.code == 1
    assert result.out["error"] == FOCUS_MISMATCH
    assert failures(result) == ["order", "dependency-order"]
    assert (root / FEATURE_JSON).read_bytes() == original


def test_focus_points_at_the_first_spec(sdd_grill, grill_project):
    root = grill_project()
    two_generated(sdd_grill, root)
    write_tree(root, {FEATURE_JSON: '{"feature_directory": "specs/002-b"}'})

    result = run_grill(sdd_grill, root, "focus")

    assert result.code == 0
    assert result.out == {"feature_directory": "specs/001-a", "previous": "specs/002-b", "changed": True}
    assert list(result.out) == ["feature_directory", "previous", "changed"]
    assert (root / FEATURE_JSON).read_bytes() == feature_json("specs/001-a")
    assert sorted(p.name for p in (root / ".specify").iterdir() if p.name.startswith(".feature")) == []


def test_focus_twice_writes_once(sdd_grill, grill_project):
    root = grill_project()
    two_generated(sdd_grill, root)
    write_tree(root, {FEATURE_JSON: feature_json("specs/001-a")})
    before = snapshot(root, with_mtime=True)

    first = run_grill(sdd_grill, root, "focus")
    second = run_grill(sdd_grill, root, "focus")

    assert first.out == second.out == {"feature_directory": "specs/001-a", "previous": "specs/001-a", "changed": False}
    assert snapshot(root, with_mtime=True) == before


@pytest.mark.parametrize("content", [None, b"not json", b"[1]", b'{"feature_directory": 3}', b'{"other": "x"}'])
def test_focus_without_a_valid_value(sdd_grill, grill_project, content):
    root = grill_project()
    two_generated(sdd_grill, root)
    if content is not None:
        write_tree(root, {FEATURE_JSON: content})

    result = run_grill(sdd_grill, root, "focus")

    assert result.code == 0
    assert result.out == {"feature_directory": "specs/001-a", "previous": None, "changed": True}
    assert (root / FEATURE_JSON).read_bytes() == feature_json("specs/001-a")


def test_focus_stops_when_feature_json_is_not_a_file(sdd_grill, grill_project):
    root = grill_project()
    two_generated(sdd_grill, root)
    (root / FEATURE_JSON).mkdir()
    before = snapshot(root)

    result = run_grill(sdd_grill, root, "focus")

    assert result.code == 1
    assert result.out["error"] == NOT_REGULAR
    assert snapshot(root) == before


def test_focus_with_a_single_spec(sdd_grill, grill_project):
    root = grill_project()
    generated(sdd_grill, root, [feature("a")], {"a": "specs/001-a"}, constitution=WRITTEN_CONSTITUTION)
    write_tree(root, {FEATURE_JSON: feature_json("specs/001-a")})

    result = run_grill(sdd_grill, root, "focus")

    assert result.out == {"feature_directory": "specs/001-a", "previous": "specs/001-a", "changed": False}


def test_feature_json_stays_out_of_git(sdd_grill, grill_project):
    root = grill_project()
    git_commit_all(root, "spec kit")
    two_generated(sdd_grill, root)
    git_commit_all(root, "specs")

    assert run_grill(sdd_grill, root, "focus").code == 0

    assert (root / FEATURE_JSON).is_file()
    assert git_status(root) == ""


def test_focus_writes_only_feature_json(sdd_grill, grill_project):
    root = grill_project()
    two_generated(sdd_grill, root)
    before = snapshot(root)

    run_grill(sdd_grill, root, "focus")

    after = snapshot(root)
    changed = {k for k in set(before) | set(after) if before.get(k, 0) != after.get(k, 0)}
    assert changed == {FEATURE_JSON}


@pytest.mark.parametrize("command", ["check", "verify", "save", "clear"])
def test_other_commands_never_write_feature_json(sdd_grill, grill_project, command):
    root = grill_project()
    two_generated(sdd_grill, root)
    write_tree(root, {FEATURE_JSON: '{"feature_directory": "specs/002-b"}'})
    progress = read_progress(root)

    stdin = json.dumps(progress) if command == "save" else None
    run_grill(sdd_grill, root, command, stdin=stdin)

    assert (root / FEATURE_JSON).read_bytes() == b'{"feature_directory": "specs/002-b"}'


def test_focus_without_features_changes_nothing(sdd_grill, grill_project):
    root = grill_project(constitution=CONSTITUTION_TEMPLATE)
    generated(sdd_grill, root, [], {}, constitution=WRITTEN_CONSTITUTION)
    write_tree(root, {FEATURE_JSON: feature_json("specs/009-x")})

    result = run_grill(sdd_grill, root, "focus")

    assert result.code == 0
    assert result.out == {"feature_directory": None, "previous": "specs/009-x", "changed": False}
    assert (root / FEATURE_JSON).read_bytes() == feature_json("specs/009-x")


# ======================================================= check: progress


def test_check_reports_saved_progress(sdd_grill, grill_project):
    root = grill_project()
    assert run_grill(sdd_grill, root, "check").out["saved"] is None
    save(sdd_grill, root, minimal_progress())

    result = run_grill(sdd_grill, root, "check")

    assert result.out["progress"] == "present"
    assert result.out["saved"] == read_progress(root)
    assert result.out["changed"] == []


def test_check_lists_what_changed_in_a_fixed_order(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs={"001-a": "a\n"})
    git_commit_all(root)
    save(sdd_grill, root, minimal_progress())

    git_commit_all(root, "another")
    assert run_grill(sdd_grill, root, "check").out["changed"] == ["head"]

    write_tree(root, {"specs/002-b/spec.md": "b\n"})
    assert run_grill(sdd_grill, root, "check").out["changed"] == ["specs", "head"]

    write_tree(root, {".specify/memory/constitution.md": "# Other\n"})
    assert run_grill(sdd_grill, root, "check").out["changed"] == ["constitution", "specs", "head"]


def test_check_sees_an_edited_spec(sdd_grill, grill_project):
    root = grill_project(specs={"001-a": "a\n"})
    save(sdd_grill, root, minimal_progress())

    write_tree(root, {"specs/001-a/spec.md": b"a\r\n"})
    assert run_grill(sdd_grill, root, "check").out["changed"] == []
    write_tree(root, {"specs/001-a/spec.md": "edited\n"})
    assert run_grill(sdd_grill, root, "check").out["changed"] == ["specs"]


def test_check_ignores_head_outside_git(sdd_grill, grill_project, monkeypatch):
    root = grill_project(git=False)
    save(sdd_grill, root, minimal_progress())
    assert run_grill(sdd_grill, root, "check").out["changed"] == []

    repo = grill_project()
    git_commit_all(repo)
    save(sdd_grill, repo, minimal_progress())
    monkeypatch.setenv("PATH", str(repo / "no-such-dir"))
    assert run_grill(sdd_grill, repo, "check").out["changed"] == []


@pytest.mark.parametrize(
    "content",
    [
        b"{not json",
        json.dumps(minimal_progress(schema=2)).encode(),
        json.dumps(minimal_progress(tool="other")).encode(),
        json.dumps(minimal_progress(stage="nowhere")).encode(),
        json.dumps(minimal_progress()).encode(),  # no fingerprint
        b"\xff\xfe",
    ],
)
def test_check_reports_unreadable_progress(sdd_grill, grill_project, content):
    root = grill_project()
    save(sdd_grill, root, minimal_progress())
    (root / PROGRESS).write_bytes(content)
    before = snapshot(root)

    result = run_grill(sdd_grill, root, "check")

    assert result.code == 0
    assert result.out["progress"] == "unreadable"
    assert result.out["saved"] is None and result.out["changed"] == []
    assert snapshot(root) == before


def test_check_reports_a_conflict(sdd_grill, grill_project):
    root = grill_project()
    save(sdd_grill, root, minimal_progress())
    write_tree(root, {OWN + "/notes.txt": "mine\n"})
    before = snapshot(root)

    result = run_grill(sdd_grill, root, "check")

    assert result.out["progress"] == "conflict"
    assert result.out["saved"] is None
    assert snapshot(root) == before


# ================================================================== clear


def test_clear_removes_the_progress_and_the_folder(sdd_grill, grill_project):
    root = grill_project()
    save(sdd_grill, root, minimal_progress())

    result = run_grill(sdd_grill, root, "clear")

    assert result.code == 0 and result.out == {"cleared": True}
    assert not (root / OWN).exists()
    assert (root / ".specify").is_dir()


def test_clear_without_progress(sdd_grill, grill_project):
    root = grill_project()
    before = snapshot(root)

    first = run_grill(sdd_grill, root, "clear")
    second = run_grill(sdd_grill, root, "clear")

    assert first.code == second.code == 0
    assert first.out == second.out == {"cleared": False}
    assert snapshot(root) == before


def test_clear_removes_unreadable_progress(sdd_grill, grill_project):
    root = grill_project()
    save(sdd_grill, root, minimal_progress())
    (root / PROGRESS).write_bytes(b"{broken")

    assert run_grill(sdd_grill, root, "clear").out == {"cleared": True}
    assert not (root / OWN).exists()


@pytest.mark.parametrize("files", [{"notes.txt": "mine\n"}, {".gitignore": "*.log\n"}])
def test_clear_deletes_nothing_on_a_conflict(sdd_grill, grill_project, files):
    root = grill_project()
    save(sdd_grill, root, minimal_progress())
    write_tree(root / OWN, files)
    before = snapshot(root)

    result = run_grill(sdd_grill, root, "clear")

    assert result.code == 1
    assert result.out["error"] == CONFLICT
    assert snapshot(root) == before


def test_clear_touches_nothing_outside_its_folder(sdd_grill, grill_project):
    root = grill_project(constitution=WRITTEN_CONSTITUTION)
    two_generated(sdd_grill, root)
    write_tree(root, {FEATURE_JSON: feature_json("specs/001-a")})
    before = {k: v for k, v in snapshot(root).items() if not k.startswith(OWN)}

    run_grill(sdd_grill, root, "clear")

    assert snapshot(root) == before


def test_clear_after_confirmation_keeps_every_generated_document(sdd_grill, grill_project):
    # Starting over from a confirmed progress whose verify keeps failing: only the progress goes.
    root = existing_project(grill_project)
    generated(
        sdd_grill,
        root,
        [feature("a"), feature("b", ["a"])],
        {"a": "specs/004-a"},
        action="amend",
        constitution=WRITTEN_CONSTITUTION + "\n- Every change MUST be reviewed.\n",
    )
    write_tree(root, {"specs/001-deploy/spec.md": "deploy, edited by hand\n"})
    write_tree(root, {FEATURE_JSON: feature_json("specs/004-a")})
    assert read_progress(root)["phase"] == "confirmed"
    assert failures(run_grill(sdd_grill, root, "verify")) == ["existing-spec-changed", "spec-missing"]
    assert sorted(p.name for p in (root / OWN).iterdir()) == [".gitignore", "progress.json"]
    before = {k: v for k, v in snapshot(root).items() if not k.startswith(OWN)}

    result = run_grill(sdd_grill, root, "clear")

    assert result.code == 0 and result.out == {"cleared": True}
    assert not (root / OWN).exists()
    assert snapshot(root) == before


# ====================================================== an existing project

EXISTING = {"001-deploy": "deploy\n", "002-claude-md": "claude md\n", "003-sdd-init": "sdd init\n"}


def existing_project(grill_project, **options):
    root = grill_project(constitution=WRITTEN_CONSTITUTION, specs=dict(EXISTING), **options)
    git_commit_all(root, "existing project")
    return root


def test_depends_on_an_existing_spec(sdd_grill, grill_project):
    root = existing_project(grill_project)
    (root / "specs/004-draft").mkdir()

    ok = save(sdd_grill, root, minimal_progress(features=[feature("x", ["specs/003-sdd-init"], status="pending")]))
    no_spec = save(sdd_grill, root, minimal_progress(features=[feature("x", ["specs/004-draft"], status="pending")]))
    absent = save(sdd_grill, root, minimal_progress(features=[feature("x", ["specs/009-none"], status="pending")]))

    assert ok.code == 0
    assert no_spec.code == 1 and absent.code == 1
    assert no_spec.out["error"].startswith("progress is invalid at features[0].depends_on[0]: ")


def test_existing_project_baseline_holds_the_existing_specs(sdd_grill, grill_project):
    root = existing_project(grill_project)

    save(sdd_grill, root, confirmed_progress([feature("x", ["specs/003-sdd-init"])], action="keep"))

    assert read_progress(root)["baseline"] == {
        "constitution": sha(WRITTEN_CONSTITUTION),
        "specs": {f"specs/{name}/spec.md": sha(content) for name, content in EXISTING.items()},
    }


def new_batch(sdd_grill, root, dirs=("specs/004-update", "specs/005-grill"), action="keep", constitution=None):
    return generated(
        sdd_grill,
        root,
        [feature("update", ["specs/003-sdd-init"]), feature("grill", ["update", "specs/001-deploy"])],
        {"update": dirs[0], "grill": dirs[1]},
        action=action,
        constitution=constitution,
    )


def test_new_specs_after_existing_ones_pass(sdd_grill, grill_project):
    root = existing_project(grill_project)
    new_batch(sdd_grill, root)

    result = run_grill(sdd_grill, root, "verify")

    assert result.code == 0, result.out
    assert result.out["specs"] == [
        {"feature": "update", "dir": "specs/004-update", "depends_on": ["specs/003-sdd-init"]},
        {"feature": "grill", "dir": "specs/005-grill", "depends_on": ["specs/004-update", "specs/001-deploy"]},
    ]
    assert result.out["unexpected"] == []


def test_existing_spec_edited_during_generation(sdd_grill, grill_project):
    root = existing_project(grill_project)
    new_batch(sdd_grill, root)
    write_tree(root, {"specs/002-claude-md/spec.md": "rewritten\n"})

    assert failures(run_grill(sdd_grill, root, "verify")) == ["existing-spec-changed"]


def test_new_spec_not_after_the_existing_ones(sdd_grill, grill_project):
    root = existing_project(grill_project)
    new_batch(sdd_grill, root, dirs=("specs/003-update", "specs/004-grill"))

    result = run_grill(sdd_grill, root, "verify")

    # 003-update is not after 003-sdd-init, which it also depends on.
    assert failures(result) == ["order", "dependency-order"]
    assert "specs/003-update" in result.out["failures"][0]["detail"]


def test_amended_constitution_passes(sdd_grill, grill_project):
    root = existing_project(grill_project)
    new_batch(sdd_grill, root, action="amend", constitution=WRITTEN_CONSTITUTION + "- Amended.\n")

    assert run_grill(sdd_grill, root, "verify").out["ok"] is True


def test_focus_points_at_the_first_spec_of_this_batch(sdd_grill, grill_project):
    root = existing_project(grill_project)
    new_batch(sdd_grill, root)
    write_tree(root, {FEATURE_JSON: feature_json("specs/005-grill")})

    result = run_grill(sdd_grill, root, "focus")

    assert result.out == {"feature_directory": "specs/004-update", "previous": "specs/005-grill", "changed": True}


def test_timestamp_numbering_in_an_existing_project(sdd_grill, grill_project):
    root = grill_project(
        constitution=WRITTEN_CONSTITUTION,
        init_options='{"feature_numbering": "timestamp"}',
        specs={"001-old": "old\n", "20261101-090000-older": "older\n"},
    )
    good = ("specs/20261120-100000-update", "specs/20261120-100010-grill")
    new_batch_dirs = {"update": good[0], "grill": good[1]}
    features = [feature("update", ["specs/001-old"]), feature("grill", ["update", "specs/20261101-090000-older"])]
    generated(sdd_grill, root, features, new_batch_dirs, action="keep")
    assert run_grill(sdd_grill, root, "verify").out["ok"] is True

    other = grill_project(
        constitution=WRITTEN_CONSTITUTION,
        init_options='{"feature_numbering": "timestamp"}',
        specs={"20261201-090000-newer": "newer\n"},
    )
    generated(sdd_grill, other, [feature("update")], {"update": good[0]}, action="keep")
    assert failures(run_grill(sdd_grill, other, "verify")) == ["order"]


# ======================================================== the real process


def test_real_run_writes_utf8_lf_json(grill_project, tmp_path):
    from conftest import real_run_env, run_grill_real

    root = grill_project()
    env = real_run_env(tmp_path / "fake-home")
    progress = json.dumps(minimal_progress(requirement="記帳工具，要簡單"), ensure_ascii=False)

    saved = run_grill_real(root, env, "save", stdin=progress)
    checked = run_grill_real(root, env, "check")
    usage = run_grill_real(root, env)

    assert saved.returncode == 0, saved.stderr
    assert checked.returncode == 0, checked.stderr
    for raw in (saved.stdout, checked.stdout):
        assert b"\r" not in raw and raw.endswith(b"}\n")
    assert json.loads(checked.stdout.decode("utf-8"))["saved"]["requirement"] == "記帳工具，要簡單"
    assert "記帳工具".encode("utf-8") in checked.stdout
    assert usage.returncode == 1 and b"usage" in usage.stderr


# ------------- a field name that looks like a secret is reported at the object that holds it

# A made-up token in the shape of a GitHub token; no real credential.
FAKE_TOKEN = "ghp_" + "Zq6FakeGrill" * 2


@pytest.mark.parametrize("name", [FAKE_TOKEN, f"{FAKE_TOKEN}.x", f"x.{FAKE_TOKEN}.y",
                                  f"https://u:{FAKE_TOKEN}@h.example.com"])
@pytest.mark.parametrize("where", ["(top level)", "features[0]", "features[0].decisions[0]"])
def test_save_does_not_repeat_a_secret_field_name(sdd_grill, grill_project, name, where):
    root = grill_project()
    progress = minimal_progress(features=[feature("a", status="discussing")], stage="feature", current_feature="a")
    holder = {"(top level)": progress, "features[0]": progress["features"][0],
              "features[0].decisions[0]": progress["features"][0]["decisions"][0]}[where]
    holder[name] = "x"
    result = save(sdd_grill, root, progress)

    assert result.code == 1
    assert result.out["error"] == (
        f"progress at {where} looks like a secret; describe what is needed instead of recording the value"
    )
    assert FAKE_TOKEN not in result.err and FAKE_TOKEN not in result.raw.decode("utf-8")
    assert not (root / PROGRESS).exists()


URL_PASSWORD = "FAKEgrillPw42"


@pytest.mark.parametrize("name", [f"https://u:{URL_PASSWORD}@h.example.invalid/", f"1.https://u:{URL_PASSWORD}@h/",
                                  f"password={URL_PASSWORD}"])
@pytest.mark.parametrize("where", ["(top level)", "constitution", "features[0]", "features[0].decisions[0]"])
def test_a_secret_field_name_is_judged_by_the_name_itself(sdd_grill, grill_project, name, where):
    """The decision is made on the field name, not on the message: the path that reaches the caller is the holder."""
    progress = minimal_progress(features=[feature("a", status="discussing")], stage="feature", current_feature="a")
    holder = {"(top level)": progress, "constitution": progress["constitution"], "features[0]": progress["features"][0],
              "features[0].decisions[0]": progress["features"][0]["decisions"][0]}[where]
    holder[name] = "x"
    with pytest.raises(sdd_grill.Invalid) as raised:
        sdd_grill.validate_progress(progress, grill_project())
    assert (raised.value.secret, raised.value.path) == (True, where)
    assert URL_PASSWORD not in str(raised.value)

    result = save(sdd_grill, grill_project(), progress)
    assert result.out["error"] == (
        f"progress at {where} looks like a secret; describe what is needed instead of recording the value"
    )
    assert URL_PASSWORD not in result.raw.decode("utf-8") and URL_PASSWORD not in result.err


def test_save_does_not_repeat_a_repeated_id_that_looks_like_a_secret(sdd_grill, grill_project):
    secret_id = "sk-" + "fakegrillid" * 3
    root = grill_project()
    progress = minimal_progress(features=[feature(secret_id, status="discussing"), feature(secret_id)],
                                stage="feature", current_feature=secret_id)
    result = save(sdd_grill, root, progress)

    assert result.code == 1
    assert result.out["error"] == (
        "progress at features[1].id looks like a secret; describe what is needed instead of recording the value"
    )
    assert secret_id not in result.raw.decode("utf-8") and secret_id not in result.err
    assert not (root / PROGRESS).exists()


# ------------- a saved progress that a maintainer edited to hold a secret is unreadable, never shown

# A made-up token in the shape of a GitHub token; no real credential.
TAINT = "ghp_" + "Zq9FakeTaint" * 2


def taint(data: dict, where: str) -> None:
    if where == "requirement":
        data["requirement"] = f"{data['requirement']} token: {TAINT}"
    elif where == "decision":
        data["features"][0]["decisions"][0]["decision"] = f"password={TAINT}"
    elif where == "rule":
        data["constitution"]["principles"][0]["rules"].append(f"use {TAINT}")
    elif where == "fingerprint key":
        data["fingerprint"]["specs"][f"specs/{TAINT}/spec.md"] = "0" * 64
    elif where == "baseline key":
        data["baseline"]["specs"][f"specs/{TAINT}/spec.md"] = "0" * 64
    elif where == "saved_at":
        data["saved_at"] = f"https://u:{TAINT}@h.example.invalid/"


@pytest.mark.parametrize("where", ["requirement", "decision", "rule", "fingerprint key", "baseline key", "saved_at"])
def test_check_does_not_show_a_progress_that_holds_a_secret(sdd_grill, grill_project, where):
    root = grill_project()
    assert save(sdd_grill, root, confirmed_progress([feature("a")])).code == 0
    data = read_progress(root)
    taint(data, where)
    (root / PROGRESS).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before = snapshot(root)

    result = run_grill(sdd_grill, root, "check")

    assert (result.code, result.out["progress"], result.out["saved"], result.out["changed"]) == (
        0, "unreadable", None, [])
    assert TAINT not in result.raw.decode("utf-8") and TAINT not in result.err
    for argv in (["verify"], ["focus"]):
        later = run_grill(sdd_grill, root, *argv)
        assert later.code == 1, argv
        assert TAINT not in later.raw.decode("utf-8") and TAINT not in later.err, argv
    assert snapshot(root) == before
    # Starting over deletes the file that holds the secret.
    assert run_grill(sdd_grill, root, "clear").out == {"cleared": True}
    assert not (root / PROGRESS).exists()


def test_save_replaces_a_progress_that_holds_a_secret(sdd_grill, grill_project):
    root = grill_project()
    save(sdd_grill, root, minimal_progress())
    data = read_progress(root)
    taint(data, "requirement")
    (root / PROGRESS).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result = save(sdd_grill, root, minimal_progress())

    assert result.code == 0 and TAINT not in result.raw.decode("utf-8")
    assert TAINT not in (root / PROGRESS).read_text(encoding="utf-8")
    assert run_grill(sdd_grill, root, "check").out["progress"] == "present"


def test_find_secret_reports_a_secret_field_name_at_its_holder(sdd_grill):
    assert sdd_grill.find_secret({"a": {TAINT: "x"}}) == "a"
    assert sdd_grill.find_secret({f"token={TAINT}": 1}) == "(top level)"
    assert sdd_grill.find_secret({"a": [{"b": {TAINT: 1}}]}) == "a[0].b"


# ------------- what save writes, every later command reads back (writing and reading are symmetric)

# Spec folder names a project may hold. Some look like secrets by the patterns (sk- followed by 20 characters, a
# made-up ghp_ token, "token=", "api-key:"); they are names of folders, not secrets the maintainer typed.
SECRET_LOOKING_SK = "004-sk-learn-pipeline-integration"
FOLDER_SETS = folder_sets_for_this_platform([
    [],
    ["001-plain"],
    [SECRET_LOOKING_SK],
    ["004-token=refresh", "005-api-key:rotation"],
    ["001-資料匯出", "002-ghp_" + "Fk3Fold" * 3, "003-a b"],
    # The name alone does not look like a secret; "specs/006-password:/spec.md" does.
    ["006-password:"],
])


def project_with_folders(grill_project, names: list[str]) -> Path:
    root = grill_project(constitution=CONSTITUTION_TEMPLATE)
    write_tree(root, {f"specs/{name}/spec.md": f"spec of {name}\n" for name in names})
    return root


def check_present(sdd_grill, root: Path) -> dict:
    result = run_grill(sdd_grill, root, "check")
    assert (result.code, result.out["progress"]) == (0, "present"), result.out
    return result.out["saved"]


@pytest.mark.parametrize("names", FOLDER_SETS, ids=lambda names: "+".join(names) or "none")
def test_every_saved_progress_reads_back_and_keeps_its_protections(sdd_grill, grill_project, names):
    root = project_with_folders(grill_project, names)
    keys = {f"specs/{name}/spec.md" for name in names}

    # discussing: save, check, save again
    assert save(sdd_grill, root, minimal_progress()).code == 0
    assert set(check_present(sdd_grill, root)["fingerprint"]["specs"]) == keys
    assert save(sdd_grill, root, minimal_progress(stage="features")).code == 0
    check_present(sdd_grill, root)

    # confirmed: the baseline is recorded once, then kept because the previous progress is read
    first = save(sdd_grill, root, confirmed_progress([feature("a")]))
    assert (first.code, first.out["baseline"]) == (0, True)
    assert set(check_present(sdd_grill, root)["baseline"]["specs"]) == keys
    again = save(sdd_grill, root, confirmed_progress([feature("a")]))
    assert (again.code, again.out["baseline"]) == (0, False)

    # generate, record spec_dir, verify and focus read the confirmed progress
    write_tree(root, {".specify/memory/constitution.md": WRITTEN_CONSTITUTION, "specs/009-a/spec.md": "spec of a\n"})
    done = save(sdd_grill, root, confirmed_progress([feature("a", spec_dir="specs/009-a")]))
    assert (done.code, done.out["baseline"]) == (0, False)
    assert set(check_present(sdd_grill, root)["baseline"]["specs"]) == keys
    verify = run_grill(sdd_grill, root, "verify")
    assert (verify.code, verify.out["ok"], verify.out["unexpected"]) == (0, True, [])
    focus = run_grill(sdd_grill, root, "focus")
    assert (focus.code, focus.out["feature_directory"]) == (0, "specs/009-a")

    # no going back to discussing once a spec was generated
    before = (root / PROGRESS).read_bytes()
    back = save(sdd_grill, root, minimal_progress(stage="summary", features=[feature("a")]))
    assert back.code == 1 and back.out["error"] == (
        "specs were already generated from the confirmed summary; it can no longer go back to discussing")
    assert (root / PROGRESS).read_bytes() == before

    # starting over works the same way
    assert run_grill(sdd_grill, root, "clear").out == {"cleared": True}
    assert save(sdd_grill, root, minimal_progress()).code == 0
    check_present(sdd_grill, root)


SCRIPT_FIELD_TAINTS = ["fingerprint key", "baseline key", "saved_at", "fingerprint value", "baseline value",
                       "fingerprint constitution", "baseline constitution", "head", "fingerprint extra key"]


def taint_script_field(data: dict, where: str) -> None:
    if where in ("fingerprint key", "baseline key", "saved_at"):
        taint(data, where)
    elif where == "fingerprint value":
        key = next(iter(data["fingerprint"]["specs"]))
        data["fingerprint"]["specs"][key] = TAINT
    elif where == "baseline value":
        key = next(iter(data["baseline"]["specs"]))
        data["baseline"]["specs"][key] = f"token: {TAINT}"
    elif where == "fingerprint constitution":
        data["fingerprint"]["constitution"] = TAINT
    elif where == "baseline constitution":
        data["baseline"]["constitution"] = TAINT
    elif where == "head":
        data["fingerprint"]["head"] = TAINT
    elif where == "fingerprint extra key":
        data["fingerprint"]["specs"][f"specs/x/spec.md password={TAINT}"] = "0" * 64


@pytest.mark.parametrize("where", SCRIPT_FIELD_TAINTS)
def test_a_secret_in_a_script_field_is_unreadable_even_beside_a_secret_looking_folder(sdd_grill, grill_project, where):
    root = project_with_folders(grill_project, [SECRET_LOOKING_SK])
    assert save(sdd_grill, root, confirmed_progress([feature("a")])).code == 0
    data = read_progress(root)
    taint_script_field(data, where)
    (root / PROGRESS).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result = run_grill(sdd_grill, root, "check")

    assert (result.code, result.out["progress"], result.out["saved"]) == (0, "unreadable", None)
    assert TAINT not in result.raw.decode("utf-8") and TAINT not in result.err


def test_a_secret_looking_folder_name_counts_only_while_the_folder_is_there(sdd_grill, grill_project):
    """A key of the fingerprint names a folder of the project; one that looks like a secret and is not there is not
    a name the script wrote from this project, so the progress is unreadable and the name is never shown."""
    root = project_with_folders(grill_project, ["001-plain"])
    assert save(sdd_grill, root, minimal_progress()).code == 0
    data = read_progress(root)
    data["fingerprint"]["specs"][f"specs/{SECRET_LOOKING_SK}/spec.md"] = "0" * 64
    data["fingerprint"]["specs"]["specs/002-gone/spec.md"] = "1" * 64
    (root / PROGRESS).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = run_grill(sdd_grill, root, "check")
    assert result.out["progress"] == "unreadable" and SECRET_LOOKING_SK not in result.raw.decode("utf-8")

    # The same folder in the project: the name is already listed by check, and the progress reads back.
    write_tree(root, {f"specs/{SECRET_LOOKING_SK}/spec.md": "x\n"})
    assert run_grill(sdd_grill, root, "check").out["progress"] == "present"
    # A folder that is gone and does not look like a secret is a change, not a reason to stop reading.
    del data["fingerprint"]["specs"][f"specs/{SECRET_LOOKING_SK}/spec.md"]
    (root / PROGRESS).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert run_grill(sdd_grill, root, "check").out["progress"] == "present"


@pytest.mark.parametrize("key", ["specs/../spec.md", "specs/./spec.md", "specs//spec.md", "specs/a/b/spec.md",
                                 "specs/a/spec.txt", "other/a/spec.md"])
def test_fingerprint_keys_have_the_form_the_script_writes(sdd_grill, grill_project, key):
    root = project_with_folders(grill_project, [])
    assert save(sdd_grill, root, minimal_progress()).code == 0
    data = read_progress(root)
    data["fingerprint"]["specs"][key] = "0" * 64
    (root / PROGRESS).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert run_grill(sdd_grill, root, "check").out["progress"] == "unreadable"


def test_a_generated_folder_named_like_a_secret_pattern_is_refused_and_renaming_gets_through(sdd_grill, grill_project):
    """Known limitation: spec_dir is sent by Claude and scanned like the rest of the progress, so save refuses a
    folder whose name has the form of a secret pattern (writing and reading agree). Renaming the folder gets through."""
    root = project_with_folders(grill_project, [])
    assert save(sdd_grill, root, confirmed_progress([feature("a"), feature("b", ["a"])])).code == 0
    write_tree(root, {".specify/memory/constitution.md": WRITTEN_CONSTITUTION,
                      "specs/001-sk-learn-pipeline-integration/spec.md": "spec of a\n"})
    before = (root / PROGRESS).read_bytes()
    refused = save(sdd_grill, root, confirmed_progress(
        [feature("a", spec_dir="specs/001-sk-learn-pipeline-integration"), feature("b", ["a"])]))
    assert refused.code == 1 and refused.out["error"].startswith("progress at features[0].spec_dir looks like a secret")
    assert (root / PROGRESS).read_bytes() == before

    (root / "specs/001-sk-learn-pipeline-integration").rename(root / "specs/001-sklearn-pipeline-integration")
    write_tree(root, {"specs/002-b/spec.md": "spec of b\n"})
    done = [feature("a", spec_dir="specs/001-sklearn-pipeline-integration"), feature("b", ["a"], spec_dir="specs/002-b")]
    assert save(sdd_grill, root, confirmed_progress(done)).code == 0
    check_present(sdd_grill, root)
    assert run_grill(sdd_grill, root, "verify").out["ok"] is True
    assert run_grill(sdd_grill, root, "focus").out["feature_directory"] == "specs/001-sklearn-pipeline-integration"
