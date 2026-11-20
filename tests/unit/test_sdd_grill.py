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
