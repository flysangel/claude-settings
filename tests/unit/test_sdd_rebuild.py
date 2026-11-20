"""Unit tests for home/skills/sdd-rebuild/scripts/sdd_rebuild.py.

The contract is specs/007-sdd-rebuild/contracts/cli.md and data-model.md. Every test runs in temporary folders:
the old project and the new project are fake projects under tmp_path, HOME points at a temporary folder and git
ignores the global and system settings (the export_env fixture).
"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (
    REPO_ROOT,
    SDD_REBUILD_PY,
    WRITTEN_CONSTITUTION,
    export_fixture,
    git_commit_all,
    keep_all_progress,
    make_rebuild_new,
    make_rebuild_old,
    place_export,
    run_rebuild,
    simulate_constitution,
    simulate_specify,
    target_item,
    tree_changes,
    tree_snapshot,
    write_tree,
)

pytestmark = pytest.mark.usefixtures("export_env")

TODAY = "2026-11-21"
NOW = "2026-11-21T08:00:00Z"
PREVIEW_ERROR = "the decisions do not yet make a valid lineage"
OWN_GITIGNORE = b"# Created by sdd-rebuild. Local rebuild progress; never committed.\n*\n"
LINEAGE_GITATTRIBUTES = b"# Created by sdd-rebuild; keeps the lineage LF on every platform.\n* text eol=lf\n"
DEFAULT_REASON = "維護者決定捨棄"


@pytest.fixture(autouse=True)
def fixed_time(sdd_rebuild, sdd_export, monkeypatch):
    monkeypatch.setattr(sdd_rebuild, "utc_today", lambda: TODAY)
    monkeypatch.setattr(sdd_rebuild, "utc_now", lambda: NOW)
    monkeypatch.setattr(sdd_export, "utc_today", lambda: "2026-11-20")


# ------------------------------------------------------------------ helpers


def gen1(tmp_path, sdd_export, **kwargs) -> Path:
    """An old project of generation 1 exported by sdd-export's real write (gen1-draft.json)."""
    return make_rebuild_old(sdd_export, tmp_path, export_fixture("gen1-draft.json"), **kwargs)


def gen2(tmp_path, sdd_export, lineage: bool = True, name: str = "old-tool") -> Path:
    """An old project holding the generation-2 nutrients fixture, with the generation-2 lineage fixture or none."""
    root = tmp_path / name
    root.mkdir()
    place_export(sdd_export, root, (REPO_ROOT / "tests/unit/fixtures/sdd_export/nutrients.json").read_bytes())
    if lineage:
        write_tree(root, {".sdd-rebuild/lineage.json": (REPO_ROOT / "tests/unit/fixtures/sdd_export/lineage-gen2.json").read_bytes()})
    return root


def nutrients_of(old: Path) -> dict:
    return json.loads((old / ".sdd-export" / "nutrients.json").read_bytes().decode("utf-8"))


def ok(result):
    assert result.code == 0, (result.out, result.err)
    return result.out


def save(module, new: Path, progress: dict, *flags: str):
    return run_rebuild(module, new, "save", *flags, stdin=progress)


def saved(new: Path) -> dict:
    return json.loads((new / ".specify" / "sdd-rebuild" / "progress.json").read_bytes().decode("utf-8"))


def started(module, tmp_path, sdd_export, old=None, new=None, **overrides):
    """Old and new project with a first save (deciding, keep everything); returns (old, new, progress)."""
    old = old or gen1(tmp_path, sdd_export)
    new = new or make_rebuild_new(tmp_path)
    nutrients = nutrients_of(old)
    lineage = "not-needed" if nutrients["generation"] == 1 else "skipped"
    progress = keep_all_progress(os.path.realpath(old), nutrients, lineage, **overrides)
    ok(save(module, new, progress))
    return old, new, progress


def confirm(module, new: Path, progress: dict) -> dict:
    progress = copy.deepcopy(progress)
    progress.update(phase="confirmed", stage="summary")
    ok(save(module, new, progress))
    return progress


def confirmed(module, tmp_path, sdd_export, **kwargs):
    old, new, progress = started(module, tmp_path, sdd_export, **kwargs)
    return old, new, confirm(module, new, progress)


def generate_all(module, new: Path, progress: dict, names=None) -> dict:
    """Constitution, then every feature's spec with claim and review, the way the skill does it."""
    progress = copy.deepcopy(progress)
    if progress["constitution"]["action"] != "keep":
        simulate_constitution(new)
        progress["generation"]["constitution"] = "written"
        ok(save(module, new, progress))
        progress["generation"]["constitution"] = "reviewed"
        ok(save(module, new, progress))
    for feature in progress["target"]["features"]:
        if feature["existing_spec"] is not None:
            continue
        simulate_specify(new, (names or {}).get(feature["id"], feature["id"]))
        out = ok(run_rebuild(module, new, "claim", feature["id"]))
        feature["spec_dir"] = out["spec_dir"]
        feature["reviewed"] = True
        ok(save(module, new, progress))
    return progress


# ------------------------------------------- (T004) usage, output, loading


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["nope"],
        ["check", "extra"],
        ["check", "--old"],
        ["check", "--old", "a", "--old", "b"],
        ["check", "--refresh-source"],
        ["save", "--old", "x"],
        ["save", "--refresh-source", "--refresh-source"],
        ["preview", "x"],
        ["claim"],
        ["claim", "a", "b"],
        ["claim", "a", "--dir"],
        ["claim", "--dir", "specs/x"],
        ["verify", "--old", "x"],
        ["lineage", "x"],
        ["focus", "x"],
        ["clear", "x"],
    ],
)
def test_usage_errors(sdd_rebuild, tmp_path, argv):
    result = run_rebuild(sdd_rebuild, tmp_path, *argv)

    assert result.code == 1
    assert result.out["reason"] == "usage"
    assert "usage" in result.err


def test_exit_codes(sdd_rebuild):
    assert (sdd_rebuild.EXIT_OK, sdd_rebuild.EXIT_FAILED, sdd_rebuild.EXIT_STATE) == (0, 1, 3)


def test_main_signature(sdd_rebuild):
    parameters = inspect.signature(sdd_rebuild.main).parameters

    assert list(parameters) == ["argv", "root", "stdin", "stdout", "stderr"]
    assert all(parameters[name].default is None for name in parameters)


def load_copy(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_loading_the_module_does_nothing(tmp_path, monkeypatch):
    before = set(sys.modules)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    module = load_copy(SDD_REBUILD_PY, "sdd_rebuild_load_check")

    assert list(work.iterdir()) == []
    assert callable(module.main)
    # neither neighbour script was loaded by the import itself
    assert module.neighbour_cache() == {}
    assert not ({"sdd_export", "sdd_grill"} & (set(sys.modules) - before))


def test_output_is_one_json_object_in_fixed_form(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    new = make_rebuild_new(tmp_path)
    result = run_rebuild(sdd_rebuild, new, "check", "--old", str(old))

    assert result.code == 0
    assert result.raw.endswith(b"\n") and not result.raw.endswith(b"\n\n")
    assert b"\r" not in result.raw
    assert result.raw.decode("utf-8") == json.dumps(result.out, ensure_ascii=False, indent=2) + "\n"
    assert "一行部署" in result.raw.decode("utf-8")  # non-ASCII is not escaped


def test_failure_writes_the_error_to_stderr_too(sdd_rebuild, tmp_path):
    new = make_rebuild_new(tmp_path)
    result = run_rebuild(sdd_rebuild, new, "preview")

    assert result.code == 1
    assert result.out["reason"] == "no-progress"
    assert result.out["error"] + "\n" == result.err


def copy_skills(tmp_path: Path, skills=("sdd-rebuild", "sdd-export", "sdd-grill"), base: Path | None = None) -> Path:
    """Copies of the skills next to each other, as tools/deploy.py installs them."""
    target = base or (tmp_path / "skills")
    for name in skills:
        shutil.copytree(REPO_ROOT / "home" / "skills" / name, target / name,
                        ignore=shutil.ignore_patterns("__pycache__"))
    return target


COMMANDS = [["check", "--old", "x"], ["save"], ["preview"], ["claim", "a"], ["verify"], ["lineage"], ["focus"], ["clear"]]


@pytest.mark.parametrize("gone", [["sdd-export"], ["sdd-grill"], ["sdd-export", "sdd-grill"]])
@pytest.mark.parametrize("argv", COMMANDS)
def test_every_command_stops_when_a_neighbour_is_missing(tmp_path, gone, argv):
    skills = copy_skills(tmp_path, [name for name in ("sdd-rebuild", "sdd-export", "sdd-grill") if name not in gone])
    module = load_copy(skills / "sdd-rebuild" / "scripts" / "sdd_rebuild.py", f"sdd_rebuild_copy_{len(gone)}_{argv[0]}")
    new = make_rebuild_new(tmp_path)
    before = tree_snapshot(new)
    result = run_rebuild(module, new, *argv, stdin="{}")

    assert result.code == 3
    assert result.out["reason"] == "dependency"
    assert result.out["missing"] == gone
    assert tree_changes(before, tree_snapshot(new)) == {"added": [], "removed": [], "changed": []}


def test_a_neighbour_that_fails_to_load_counts_as_missing(tmp_path):
    skills = copy_skills(tmp_path)
    (skills / "sdd-grill" / "scripts" / "sdd_grill.py").write_text("raise RuntimeError('broken')\n")
    module = load_copy(skills / "sdd-rebuild" / "scripts" / "sdd_rebuild.py", "sdd_rebuild_broken_neighbour")
    result = run_rebuild(module, make_rebuild_new(tmp_path), "clear")

    assert (result.code, result.out["reason"], result.out["missing"]) == (3, "dependency", ["sdd-grill"])


def test_dependency_check_output_keeps_the_check_keys(tmp_path):
    skills = copy_skills(tmp_path, ["sdd-rebuild", "sdd-grill"])
    module = load_copy(skills / "sdd-rebuild" / "scripts" / "sdd_rebuild.py", "sdd_rebuild_dep_check")
    result = run_rebuild(module, make_rebuild_new(tmp_path), "check", "--old", str(tmp_path))

    assert result.out["dependencies"] == {"sdd-export": "missing", "sdd-grill": "ok"}
    assert result.out["missing"] == ["sdd-export"]
    assert result.out["next"] is None


def test_neighbours_are_found_from_the_script_location_once_deployed(tmp_path, sdd_export):
    home = tmp_path / "deployed-home"
    skills = copy_skills(tmp_path, base=home / ".claude" / "skills")
    module = load_copy(skills / "sdd-rebuild" / "scripts" / "sdd_rebuild.py", "sdd_rebuild_deployed")
    old = gen1(tmp_path, sdd_export)
    result = run_rebuild(module, make_rebuild_new(tmp_path), "check", "--old", str(old))

    assert result.code == 0, result.out
    assert result.out["dependencies"] == {"sdd-export": "ok", "sdd-grill": "ok"}
    assert result.out["export_skill"] is True


# --------------------------------------------- (T006) ancestors and expand


def anc_table(**entries) -> dict:
    return {key.replace("_", "-"): value for key, value in entries.items()}


def test_expand_puts_direct_sources_first_then_depth_first_ancestors(sdd_rebuild):
    # research.md "實測紀錄" 5: files-all was merged from files-list and diff-mark at export time; both were split
    # out of overview-list, which had been merged from status-list and report-diff.
    ancestors = anc_table(
        files_list=["overview-list", "status-list", "report-diff"],
        diff_mark=["overview-list", "status-list", "report-diff"],
        overview_list=["status-list", "report-diff"],
    )

    assert sdd_rebuild.expand(["files-list", "diff-mark"], ancestors) == [
        "files-list", "diff-mark", "overview-list", "status-list", "report-diff"]


def test_expand_visits_each_direct_source_in_order_preorder(sdd_rebuild):
    ancestors = {"a": ["a1", "a2"], "a1": ["a11"], "b": ["b1"], "a2": ["b1"]}

    assert sdd_rebuild.expand(["a", "b"], ancestors) == ["a", "b", "a1", "a11", "a2", "b1"]


def test_expand_removes_duplicates_keeping_the_first_place(sdd_rebuild):
    assert sdd_rebuild.expand(["a", "b", "a"], {"b": ["a", "c"]}) == ["a", "b", "c"]


def test_expand_of_unknown_ids_is_just_the_direct_list(sdd_rebuild):
    assert sdd_rebuild.expand(["x", "y"], {}) == ["x", "y"]
    assert sdd_rebuild.expand([], {"x": ["y"]}) == []


def test_expand_ends_on_a_cycle(sdd_rebuild):
    ancestors = {"a": ["b"], "b": ["c"], "c": ["a", "d"]}

    assert sdd_rebuild.expand(["a"], ancestors) == ["a", "b", "c", "d"]


def test_expand_handles_a_long_chain(sdd_rebuild):
    ancestors = {f"i{n}": [f"i{n + 1}"] for n in range(5000)}

    assert len(sdd_rebuild.expand(["i0"], ancestors)) == 5001


@pytest.mark.parametrize(
    "direct, ancestors",
    [
        (["a", "b"], {"a": ["c", "d"], "c": ["e"], "b": ["d", "f"]}),
        (["x"], {"x": ["y"], "y": ["x", "z"]}),
        (["p", "p", "q"], {"q": ["p"]}),
        ([], {}),
    ],
)
def test_expand_properties(sdd_rebuild, direct, ancestors):
    result = sdd_rebuild.expand(direct, ancestors)
    unique_direct = list(dict.fromkeys(direct))
    known = set(direct) | set(ancestors) | {a for values in ancestors.values() for a in values}

    assert len(result) == len(set(result))
    assert result[: len(unique_direct)] == unique_direct
    assert sdd_rebuild.expand(result, ancestors) == result
    assert set(result) <= known


def nutrients_with(sdd_export_module, **sections) -> dict:
    data = export_fixture("nutrients.json")
    data.update(sections)
    return data


def test_ancestors_come_from_the_nutrients(sdd_rebuild):
    nutrients = export_fixture("gen3-draft.json")
    ancestors = sdd_rebuild.build_ancestors(nutrients, None)

    assert ancestors["overview"] == ["status", "report"]
    assert ancestors["overview-list"] == ["status-list", "report-diff"]
    assert ancestors["deploy"] == []
    assert "audit" not in ancestors  # discarded items are not active


def test_ancestors_join_the_old_lineage_nutrients_first(sdd_rebuild):
    nutrients = {"generation": 2, "principles": [], "lessons": [], "discarded": [], "features": [
        {"id": "f", "derived_from": ["a", "b"], "requirements": [{"id": "r", "derived_from": ["x"]}]}]}
    lineage = {"generation": 2, "principles": [], "lessons": [], "discarded": [], "features": [
        {"id": "f", "derived_from": ["b", "c"], "requirements": [{"id": "r", "derived_from": []}, {"id": "q", "derived_from": ["z"]}]},
        {"id": "g", "derived_from": ["y"], "requirements": []}]}

    ancestors = sdd_rebuild.build_ancestors(nutrients, lineage)

    assert ancestors == {"f": ["a", "b", "c"], "r": ["x"], "q": ["z"], "g": ["y"]}
    assert sdd_rebuild.build_ancestors(nutrients, None) == {"f": ["a", "b"], "r": ["x"]}


@pytest.mark.parametrize("basis, expected", [("inherit", ["a", "b", "c"]), ("derived", ["f", "a", "c", "b"]), ("new", [])])
def test_derived_from_of_each_basis(sdd_rebuild, basis, expected):
    ancestors = {"f": ["a", "b"], "a": ["c"]}
    entry = {"id": "f" if basis == "inherit" else "n", "basis": basis, "from": ["f"] if basis == "derived" else []}

    assert sdd_rebuild.derived_from_of(entry, ancestors) == expected


def test_kept_items_stay_the_same_when_applied_twice(sdd_rebuild):
    ancestors = {"f": ["a", "b"], "a": ["c"], "b": ["c", "d"]}
    once = sdd_rebuild.derived_from_of({"id": "f", "basis": "inherit", "from": []}, ancestors)
    again = sdd_rebuild.derived_from_of({"id": "f", "basis": "inherit", "from": []}, {**ancestors, "f": once})

    assert once == again == ["a", "b", "c", "d"]


# ---------------------------------------------- (T007) composing a lineage


def snapshot_of(nutrients: dict, lineage: dict | None = None, state: str = "none") -> dict:
    return {"nutrients": nutrients, "nutrients_sha256": "0" * 64, "lineage_state": state, "lineage": lineage,
            "lineage_sha256": None}


def plan(nutrients: dict, old_lineage: str = "skipped", **overrides) -> dict:
    progress = keep_all_progress("/old", nutrients, old_lineage, **overrides)
    progress["rebuilt_at"] = "2026-11-21"
    for feature in progress["target"]["features"]:
        feature["spec_dir"] = f"specs/00{progress['target']['features'].index(feature) + 1}-{feature['id']}"
    return progress


def by_id(lineage: dict) -> dict:
    return {item["id"]: item for section in ("principles", "features", "lessons")
            for item in lineage[section]} | {r["id"]: r for f in lineage["features"] for r in f["requirements"]}


def test_compose_top_level_fields(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    lineage = sdd_rebuild.compose_lineage(snapshot_of(nutrients), plan(nutrients))

    assert list(lineage) == ["tool", "schema", "generation", "rebuilt_at", "source", "principles", "features",
                             "lessons", "discarded"]
    assert (lineage["tool"], lineage["schema"], lineage["generation"], lineage["rebuilt_at"]) == (
        "sdd-rebuild", 1, 3, "2026-11-21")
    assert lineage["source"] == {"project": "my-tool", "generation": 2, "nutrients_schema": 1}


def test_compose_inherit_keeps_the_source_fields(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    lineage = sdd_rebuild.compose_lineage(snapshot_of(nutrients), plan(nutrients))
    items = by_id(lineage)
    deploy = items["deploy"]

    assert deploy == {
        "id": "deploy", "origin": 1, "title": "一行部署", "summary": "維護者以一行指令把設定安裝到家目錄。",
        "revised": [2], "derived_from": [], "source": "spec", "spec_dir": "specs/001-deploy",
        "spec": "specs/001-deploy/spec.md", "depends_on": [], "requirements": [deploy["requirements"][0]],
    }
    assert items["status-report-diff"] == {"id": "status-report-diff", "origin": 2, "kind": "functional",
                                           "text": "列出與來源內容不同的已部署檔案。", "revised": [],
                                           "derived_from": [], "source": "code"}
    assert "status" not in json.dumps(lineage).replace("status-report", "")  # no status, no evidence
    assert "evidence" not in json.dumps(lineage)
    assert items["atomic-write"] == {"id": "atomic-write", "origin": 1, "kind": "pitfall",
                                     "title": "寫入中斷留下半份檔案", "text": nutrients["lessons"][0]["text"],
                                     "revised": [], "derived_from": []}


@pytest.mark.parametrize("field", ["title", "summary"])
def test_compose_inherit_with_changed_content_marks_this_generation(sdd_rebuild, field):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    progress["target"]["features"][0][field] = "新的內容"
    deploy = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress))["deploy"]

    assert deploy[field] == "新的內容"
    assert deploy["revised"] == [2, 3]


def test_compose_inherit_with_the_same_content_written_out_is_not_a_change(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    progress["target"]["features"][0]["title"] = "一行部署"
    progress["target"]["lessons"][0]["kind"] = "decision"

    items = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress))
    assert items["deploy"]["revised"] == [2]
    assert items["atomic-write"]["kind"] == "decision" and items["atomic-write"]["revised"] == []


def test_compose_derived_items(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    deploy, report = progress["target"]["features"]
    merged = {"id": "deploy-all", "basis": "derived", "from": ["status-report", "deploy"], "title": "部署與報告",
              "summary": "部署並報告。", "depends_on": [], "existing_spec": None, "spec_dir": "specs/001-deploy-all",
              "reviewed": False, "requirements": [
                  {"id": "deploy-no-overwrite", "basis": "inherit", "from": [], "kind": None, "text": None},
                  {"id": "deploy-report", "basis": "derived", "from": ["status-report-diff"], "kind": "functional",
                   "text": "列出差異。"}]}
    progress["target"]["features"] = [merged]
    progress["pending_decided"] = ["status-report-diff"]
    items = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress))

    assert items["deploy-all"]["origin"] == 3 and items["deploy-all"]["revised"] == []
    assert items["deploy-all"]["derived_from"] == ["status-report", "deploy"]
    assert items["deploy-all"]["source"] == "code"  # the first direct source's
    assert items["deploy-all"]["spec"] == "specs/001-deploy/spec.md"  # the first direct source with a spec
    assert items["deploy-report"] == {"id": "deploy-report", "origin": 3, "kind": "functional", "text": "列出差異。",
                                      "revised": [], "derived_from": ["status-report-diff"], "source": "code"}


def test_compose_derived_lesson_has_no_source_and_spec_null_without_sources(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    progress["target"]["lessons"] = [{"id": "write-safely", "basis": "derived", "from": ["atomic-write"],
                                      "kind": "decision", "title": "安全寫入", "text": "寫暫存檔再取代。"}]
    progress["target"]["features"][1] = {**progress["target"]["features"][1], "id": "report", "basis": "derived",
                                         "from": ["status-report"], "title": "報告", "summary": "報告。"}
    items = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress))

    assert "source" not in items["write-safely"]
    assert items["report"]["spec"] is None


def test_compose_new_items(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    progress["target"]["principles"].append({"id": "small", "basis": "new", "from": [], "title": "小", "text": "MUST 小。"})
    items = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress))

    assert items["small"] == {"id": "small", "origin": 3, "title": "小", "text": "MUST 小。", "revised": [],
                              "derived_from": [], "source": "rebuild"}


def test_compose_new_feature_has_spec_null(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    progress["target"]["features"].append({"id": "audit", "basis": "new", "from": [], "title": "稽核", "summary": "稽核。",
                                           "depends_on": ["deploy"], "existing_spec": None, "spec_dir": None,
                                           "reviewed": False, "requirements": [
                                               {"id": "audit-log", "basis": "new", "from": [], "kind": "functional",
                                                "text": "記錄。"}]})
    audit = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress))["audit"]

    assert (audit["source"], audit["spec"], audit["spec_dir"], audit["depends_on"]) == ("rebuild", None, None, ["deploy"])


def test_compose_discarded(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    progress["target"]["lessons"] = []
    progress["target"]["features"][0]["requirements"] = []
    progress["discards"] = [{"id": "atomic-write", "text": None, "reason": None},
                            {"id": "deploy-no-overwrite", "text": "不覆蓋。", "reason": "不再需要。"}]
    lineage = sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress)

    assert lineage["discarded"] == [
        nutrients["discarded"][0],
        {"id": "atomic-write", "kind": "lesson", "origin": 1, "discarded_in": 3, "text": "寫入中斷留下半份檔案",
         "reason": DEFAULT_REASON},
        {"id": "deploy-no-overwrite", "kind": "requirement", "origin": 1, "discarded_in": 3, "text": "不覆蓋。",
         "reason": "不再需要。"},
    ]


def test_compose_discarded_requirement_text_defaults_to_its_first_line(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    nutrients["features"][0]["requirements"][0]["text"] = "第一行" + "長" * 100 + "\n第二行"
    progress = plan(nutrients)
    progress["target"]["features"][0]["requirements"] = []
    progress["discards"] = [{"id": "deploy-no-overwrite", "text": None, "reason": None}]
    record = sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress)["discarded"][-1]

    assert record["text"] == ("第一行" + "長" * 100)[:80]


def test_default_reason_constant(sdd_rebuild):
    assert sdd_rebuild.DEFAULT_DISCARD_REASON == DEFAULT_REASON


def test_compose_serializes_the_same_bytes_twice(sdd_rebuild, sdd_export):
    nutrients = export_fixture("nutrients.json")
    first = sdd_export.serialize(sdd_rebuild.compose_lineage(snapshot_of(nutrients), plan(nutrients)), "lineage")
    second = sdd_export.serialize(sdd_rebuild.compose_lineage(snapshot_of(copy.deepcopy(nutrients)), plan(nutrients)), "lineage")

    assert first == second
    assert sdd_export.lineage_problems(json.loads(first)) == []


def test_compose_with_placeholders_fills_the_undecided_values(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    progress["rebuilt_at"] = None
    progress["target"]["features"][1]["spec_dir"] = None

    plain = sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress)
    filled = sdd_rebuild.compose_lineage(snapshot_of(nutrients), progress, placeholders=True)
    assert plain["rebuilt_at"] is None and plain["features"][1]["spec_dir"] is None
    assert filled["rebuilt_at"] == TODAY and filled["features"][1]["spec_dir"] == "specs/pending"


def test_compose_uses_the_old_lineage_only_when_used(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    old = {"generation": 2, "principles": [], "lessons": [], "discarded": [], "features": [
        {"id": "deploy", "derived_from": ["ancient"], "requirements": []}]}
    used = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients, old, "present"), plan(nutrients, "used")))
    skipped = by_id(sdd_rebuild.compose_lineage(snapshot_of(nutrients, old, "present"), plan(nutrients, "skipped")))

    assert used["deploy"]["derived_from"] == ["ancient"]
    assert skipped["deploy"]["derived_from"] == []


# ------------------------------------------ (T008) used ids and the checks


def run_checks(module, nutrients, progress, root=None, lineage=None, state="none"):
    return module.preview_problems(snapshot_of(nutrients, lineage, state), progress, root)


def names(problems) -> list[str]:
    return [problem["check"] for problem in problems]


def gen2_progress(**changes):
    nutrients = export_fixture("nutrients.json")
    progress = plan(nutrients)
    for key, value in changes.items():
        progress[key] = value
    return nutrients, progress


def test_the_keep_all_plan_passes_every_check(sdd_rebuild):
    nutrients, progress = gen2_progress()

    assert run_checks(sdd_rebuild, nutrients, progress) == []


def test_used_ids_from_the_nutrients(sdd_rebuild):
    nutrients = export_fixture("gen3-draft.json")
    used = sdd_rebuild.used_ids(nutrients, None, sdd_rebuild.build_ancestors(nutrients, None), None, [])

    assert {"deploy", "overview", "overview-list", "atomic-write", "audit", "audit-log", "json-format", "status",
            "report", "status-list", "report-diff"} <= used


def test_used_ids_from_the_old_lineage(sdd_rebuild):
    nutrients = export_fixture("nutrients.json")
    old = {"generation": 2, "principles": [], "lessons": [], "discarded": [{"id": "gone"}], "features": [
        {"id": "old-only", "derived_from": ["older"], "requirements": []}]}
    used = sdd_rebuild.used_ids(nutrients, old, {}, None, [])

    assert {"gone", "old-only", "older"} <= used


def test_used_ids_from_the_expanded_ancestors(sdd_rebuild):
    used = sdd_rebuild.used_ids(export_fixture("nutrients.json"), None, {"x": ["y", "z"]}, None, [])

    assert {"x", "y", "z"} <= used


def test_used_ids_from_the_composed_lineage(sdd_rebuild):
    lineage = {"principles": [], "lessons": [], "discarded": [], "features": [
        {"id": "kept", "derived_from": ["far"], "requirements": [{"id": "r", "derived_from": ["near"]}]}]}
    used = sdd_rebuild.used_ids({"principles": [], "features": [], "lessons": [], "discarded": []}, None, {}, lineage,
                                ["kept"])

    assert {"kept", "far", "near"} <= used and "r" not in used


def test_id_taken_catches_reuse_of_another_items_expanded_source_that_006_misses(sdd_rebuild, sdd_export):
    # The old lineage records that deploy came from "legacy"; a new item named "legacy" in the same lineage is not
    # seen by 006 (rule 9 looks only at the earlier L and N), so 007 refuses it.
    nutrients = export_fixture("nutrients.json")
    old = {"generation": 2, "principles": [], "lessons": [], "discarded": [], "features": [
        {"id": "deploy", "derived_from": ["legacy"], "requirements": []}]}
    progress = plan(nutrients, "used")
    progress["target"]["principles"].append({"id": "legacy", "basis": "new", "from": [], "title": "舊", "text": "舊。"})
    lineage = sdd_rebuild.compose_lineage(snapshot_of(nutrients, old, "present"), progress, placeholders=True)

    assert sdd_export.generation_problems(lineage, lineage, None) == []
    problems = run_checks(sdd_rebuild, nutrients, progress, lineage=old, state="present")
    assert names(problems) == ["id-taken"]
    assert problems[0]["path"] == "target.principles[1].id"


def test_inherit_unknown(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["principles"][0]["id"] = "nothing"
    progress["target"]["lessons"][0]["id"] = "deploy"  # exists, but as a feature

    problems = run_checks(sdd_rebuild, nutrients, progress)
    assert names(problems).count("inherit-unknown") == 2
    assert "unaccounted" in names(problems)


def test_inherit_twice(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["principles"].append(dict(progress["target"]["principles"][0]))

    assert "inherit-twice" in names(run_checks(sdd_rebuild, nutrients, progress))


def test_from_unknown_and_from_of_another_kind(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["principles"].append({"id": "p-new", "basis": "derived", "from": ["deploy"], "title": "x", "text": "y"})
    progress["target"]["lessons"].append({"id": "l-new", "basis": "derived", "from": ["missing"], "kind": "decision",
                                          "title": "x", "text": "y"})

    problems = [p for p in run_checks(sdd_rebuild, nutrients, progress) if p["check"] == "from-unknown"]
    assert [p["path"] for p in problems] == ["target.principles[1].from[0]", "target.lessons[1].from[0]"]


def test_requirement_from_must_be_a_requirement(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["features"][0]["requirements"].append(
        {"id": "r-new", "basis": "derived", "from": ["status-report"], "kind": "functional", "text": "x"})

    assert "from-unknown" in names(run_checks(sdd_rebuild, nutrients, progress))


def test_unaccounted(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["lessons"] = []

    problems = run_checks(sdd_rebuild, nutrients, progress)
    assert names(problems) == ["unaccounted"]
    assert "atomic-write" in problems[0]["detail"]


def test_an_item_in_a_from_is_accounted_for(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["lessons"] = [{"id": "new-lesson", "basis": "derived", "from": ["atomic-write"],
                                      "kind": "decision", "title": "x", "text": "y"}]

    assert run_checks(sdd_rebuild, nutrients, progress) == []


@pytest.mark.parametrize("case", ["unknown", "kept", "in-from", "twice"])
def test_discard_conflict(sdd_rebuild, case):
    nutrients, progress = gen2_progress()
    if case == "unknown":
        progress["discards"] = [{"id": "nothing", "text": None, "reason": None}]
    elif case == "kept":
        progress["discards"] = [{"id": "atomic-write", "text": None, "reason": None}]
    elif case == "in-from":
        progress["target"]["lessons"] = [{"id": "new-lesson", "basis": "derived", "from": ["atomic-write"],
                                          "kind": "decision", "title": "x", "text": "y"}]
        progress["discards"] = [{"id": "atomic-write", "text": None, "reason": None}]
    else:
        progress["target"]["lessons"] = []
        progress["discards"] = [{"id": "atomic-write", "text": None, "reason": None}] * 2

    assert "discard-conflict" in names(run_checks(sdd_rebuild, nutrients, progress))


def test_discarding_passes(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["lessons"] = []
    progress["discards"] = [{"id": "atomic-write", "text": None, "reason": None}]

    assert run_checks(sdd_rebuild, nutrients, progress) == []


def test_pending_undecided(sdd_rebuild):
    nutrients, progress = gen2_progress(pending_decided=[])

    problems = run_checks(sdd_rebuild, nutrients, progress)
    assert names(problems) == ["pending-undecided"]
    assert "status-report-diff" in problems[0]["detail"]


@pytest.mark.parametrize("taken", ["deploy", "deploy-symlink", "cross-platform"])
def test_id_taken_for_new_and_derived(sdd_rebuild, taken):
    nutrients, progress = gen2_progress()
    progress["target"]["principles"][0]["id"] = "other" if taken == "cross-platform" else "cross-platform"
    if taken == "cross-platform":
        progress["target"]["principles"][0] = {"id": "cross-platform", "basis": "new", "from": [], "title": "x", "text": "y"}
        progress["target"]["principles"].append(target_item(nutrients["principles"][0], "principles"))
        progress["target"]["principles"][1]["id"] = "cross-platform"
    else:
        progress["target"]["principles"].append({"id": taken, "basis": "new", "from": [], "title": "x", "text": "y"})

    assert "id-taken" in names(run_checks(sdd_rebuild, nutrients, progress))


def test_new_ids_that_are_fresh_pass(sdd_rebuild):
    nutrients, progress = gen2_progress()
    progress["target"]["principles"].append({"id": "fresh", "basis": "new", "from": [], "title": "x", "text": "y"})

    assert run_checks(sdd_rebuild, nutrients, progress) == []


def test_existing_spec_checks(sdd_rebuild, tmp_path):
    new = make_rebuild_new(tmp_path, specs={"001-deploy": "# spec\n", "002-other": "# spec\n"})
    (new / "specs" / "003-empty").mkdir()
    nutrients, progress = gen2_progress()
    deploy, report = progress["target"]["features"]

    deploy["existing_spec"] = "specs/001-deploy"
    assert run_checks(sdd_rebuild, nutrients, progress, root=new) == []

    for value in ("specs/009-none", "specs/003-empty"):
        deploy["existing_spec"] = value
        assert names(run_checks(sdd_rebuild, nutrients, progress, root=new)) == ["existing-spec"]

    deploy["existing_spec"] = report["existing_spec"] = "specs/001-deploy"
    assert "existing-spec" in names(run_checks(sdd_rebuild, nutrients, progress, root=new))

    deploy["existing_spec"], report["existing_spec"] = None, "specs/002-other"
    assert "existing-spec" in names(run_checks(sdd_rebuild, nutrients, progress, root=new))


def test_lineage_format_and_next_export_use_006(sdd_rebuild, sdd_export, monkeypatch):
    nutrients, progress = gen2_progress()
    progress["target"]["features"][1]["spec_dir"] = None
    seen = {}

    def lineage_problems(data):
        seen["spec_dir"] = data["features"][1]["spec_dir"]
        return [sdd_export.Problem("field", "features[0].title", "broken")]

    monkeypatch.setattr(sdd_export, "lineage_problems", lineage_problems)
    monkeypatch.setattr(sdd_export, "generation_problems",
                        lambda draft, lineage, existing: [sdd_export.Problem("id-reused", "features[0].id", "reused")])
    problems = run_checks(sdd_rebuild, nutrients, progress)

    assert names(problems) == ["lineage-format", "next-export"]
    assert seen["spec_dir"] == "specs/pending"
    assert [p["path"] for p in problems] == ["lineage.features[0].title", "lineage.features[0].id"]


def test_006_checks_run_only_when_007_checks_pass(sdd_rebuild, sdd_export, monkeypatch):
    nutrients, progress = gen2_progress(pending_decided=[])
    monkeypatch.setattr(sdd_export, "lineage_problems", lambda data: [sdd_export.Problem("field", "x", "y")])

    assert names(run_checks(sdd_rebuild, nutrients, progress)) == ["pending-undecided"]


def test_every_problem_is_listed_at_once(sdd_rebuild):
    nutrients, progress = gen2_progress(pending_decided=[])
    progress["target"]["lessons"] = []
    progress["discards"] = [{"id": "nothing", "text": None, "reason": None}]

    assert set(names(run_checks(sdd_rebuild, nutrients, progress))) == {"unaccounted", "discard-conflict",
                                                                        "pending-undecided"}


def test_problem_format(sdd_rebuild):
    nutrients, progress = gen2_progress(pending_decided=[])

    for problem in run_checks(sdd_rebuild, nutrients, progress):
        assert list(problem) == ["check", "path", "detail"]
        assert all(isinstance(value, str) for value in problem.values())


# ------------------------------------------------------- (T013) check, A

CHECK_KEYS = [
    "dependencies", "export_skill", "speckit", "missing", "constitution", "numbering", "specs", "rebuild_dir",
    "rebuild_conflicts", "progress", "changed", "saved", "old", "export_dir", "nutrients_edited", "nutrients_errors",
    "conflicts", "nutrients", "pending", "old_lineage", "old_lineage_errors", "needs_old_lineage", "source_state",
    "source_changed", "source_diff", "next",
]


def check(module, new: Path, old: Path | str | None = None):
    argv = ["check"] + (["--old", str(old)] if old is not None else [])
    return run_rebuild(module, new, *argv)


def test_check_first_generation(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    new = make_rebuild_new(tmp_path)
    out = ok(check(sdd_rebuild, new, old))

    assert list(out) == CHECK_KEYS
    assert out["dependencies"] == {"sdd-export": "ok", "sdd-grill": "ok"}
    assert out["export_skill"] is True
    assert (out["speckit"], out["missing"], out["constitution"], out["numbering"], out["specs"]) == (
        "ok", [], "missing", "sequential", [])
    assert (out["rebuild_dir"], out["rebuild_conflicts"], out["progress"], out["changed"], out["saved"]) == (
        "none", [], "none", [], None)
    assert out["old"] == {"path": os.path.realpath(old), "state": "ok"}
    assert (out["export_dir"], out["nutrients_edited"], out["nutrients_errors"], out["conflicts"]) == ("ours", False, [], [])
    assert out["nutrients"] == nutrients_of(old)
    assert (out["pending"], out["old_lineage"], out["old_lineage_errors"], out["needs_old_lineage"]) == ([], "none", [], False)
    assert (out["source_state"], out["source_changed"], out["source_diff"]) == (None, None, None)
    assert out["next"] == {"step": "start", "feature": None, "candidates": []}


def test_check_second_generation_without_its_lineage(sdd_rebuild, tmp_path, sdd_export):
    # quickstart.md "腳本的手動檢查"
    out = ok(check(sdd_rebuild, make_rebuild_new(tmp_path), gen2(tmp_path, sdd_export, lineage=False)))

    assert (out["export_dir"], out["old_lineage"], out["needs_old_lineage"], out["next"]["step"]) == (
        "ours", "none", True, "start")
    assert out["pending"] == ["status-report-diff"]


def test_check_reports_spec_kit_state_like_sdd_grill(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    new = make_rebuild_new(tmp_path, constitution=WRITTEN_CONSTITUTION, specs={"001-a": "# a\n"},
                           init_options='{"feature_numbering": "timestamp"}')
    out = ok(check(sdd_rebuild, new, old))

    assert (out["constitution"], out["numbering"], out["specs"]) == ("written", "timestamp",
                                                                      [{"dir": "specs/001-a", "number": "001"}])


def test_check_without_spec_kit(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    new = tmp_path / "plain"
    new.mkdir()
    result = check(sdd_rebuild, new, old)

    assert (result.code, result.out["reason"], result.out["speckit"]) == (3, "speckit-missing", "missing")
    assert result.out["export_dir"] == "ours"  # what can be told is still reported


def test_check_with_incomplete_spec_kit(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, omit=(".specify/templates/spec-template.md",))
    result = check(sdd_rebuild, new, gen1(tmp_path, sdd_export))

    assert (result.code, result.out["reason"]) == (3, "speckit-incomplete")
    assert result.out["missing"] == [".specify/templates/spec-template.md"]


def test_check_needs_an_old_project(sdd_rebuild, tmp_path):
    result = check(sdd_rebuild, make_rebuild_new(tmp_path))

    assert (result.code, result.out["reason"]) == (3, "old-required")
    assert result.out["old"] == {"path": None, "state": None}
    assert result.out["export_dir"] is None and result.out["nutrients"] is None


def test_check_old_project_missing_or_not_a_folder(sdd_rebuild, tmp_path):
    new = make_rebuild_new(tmp_path)
    missing = check(sdd_rebuild, new, tmp_path / "nowhere")
    (tmp_path / "a-file").write_text("x")
    not_folder = check(sdd_rebuild, new, tmp_path / "a-file")

    assert (missing.code, missing.out["reason"], missing.out["old"]["state"]) == (3, "old-missing", "missing")
    assert (not_folder.code, not_folder.out["reason"], not_folder.out["old"]["state"]) == (3, "old-not-folder", "not-folder")
    assert missing.out["export_dir"] is None


def test_check_same_or_nested_projects(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path)
    place_export(sdd_export, new, export_fixture("nutrients.json"))
    inner = new / "inner"
    inner.mkdir()
    outer_new = make_rebuild_new(tmp_path / "outer", name="inside")

    same = run_rebuild(sdd_rebuild, new, "check", "--old", ".")
    old_inside = check(sdd_rebuild, new, inner)
    new_inside = check(sdd_rebuild, outer_new, tmp_path / "outer")

    assert (same.code, same.out["reason"], same.out["old"]["state"]) == (3, "same-project", "same")
    assert (old_inside.out["reason"], old_inside.out["old"]["state"]) == ("old-inside-new", "old-inside-new")
    assert (new_inside.out["reason"], new_inside.out["old"]["state"]) == ("new-inside-old", "new-inside-old")
    assert same.out["export_dir"] is None  # the old project is not read at all


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32", reason="symbolic links")
def test_check_same_project_through_a_symbolic_link(sdd_rebuild, tmp_path):
    new = make_rebuild_new(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(new, target_is_directory=True)
    result = check(sdd_rebuild, new, link)

    assert result.out["reason"] == "same-project"
    assert result.out["old"]["path"] == os.path.realpath(new)


def test_check_same_project_written_differently(sdd_rebuild, tmp_path):
    new = make_rebuild_new(tmp_path)
    result = check(sdd_rebuild, new, str(new / "specs" / ".." / "." ) + os.sep)

    assert result.out["reason"] == "same-project"


def test_paths_compare_without_case_on_windows(sdd_rebuild, tmp_path, monkeypatch):
    # A stand-in for Windows: two folders whose names differ only in case are the same folder there.
    upper, lower = tmp_path / "Proj", tmp_path / "proj"
    upper.mkdir()
    lower.mkdir()
    write_tree(lower, {".specify/x": "x"})
    monkeypatch.setattr(sdd_rebuild, "fold_case", lambda: True)

    assert sdd_rebuild.relation(lower, upper) == "same"
    assert sdd_rebuild.relation(lower, tmp_path / "PROJ" / "sub") == "old-inside-new"
    monkeypatch.setattr(sdd_rebuild, "fold_case", lambda: False)
    assert sdd_rebuild.relation(lower, upper) == "ok"


def test_check_accepts_a_relative_old_path(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    new = make_rebuild_new(tmp_path)
    out = ok(run_rebuild(sdd_rebuild, new, "check", "--old", os.path.join("..", old.name)))

    assert out["old"]["path"] == os.path.realpath(old)


def test_check_old_project_without_nutrients(sdd_rebuild, tmp_path):
    old = make_rebuild_old(None, tmp_path, None) if False else tmp_path / "bare"
    old.mkdir()
    new = make_rebuild_new(tmp_path)
    none = ok(check(sdd_rebuild, new, old))
    (old / ".sdd-export").mkdir()
    empty = ok(check(sdd_rebuild, new, old))

    assert (none["export_dir"], none["nutrients"], none["next"]["step"]) == ("none", None, "start")
    assert empty["export_dir"] == "empty"
    assert none["old_lineage"] == "none" and none["needs_old_lineage"] is None


@pytest.mark.parametrize("case", ["file", "stranger", "attributes-only", "not-ours"])
def test_check_rebuild_dir_conflict(sdd_rebuild, tmp_path, sdd_export, case):
    new = make_rebuild_new(tmp_path)
    if case == "file":
        write_tree(new, {".sdd-rebuild": "x"})
    elif case == "stranger":
        write_tree(new, {".sdd-rebuild/notes.txt": "x", ".sdd-rebuild/lineage.json": export_fixture_bytes("lineage-gen2.json")})
    elif case == "attributes-only":
        write_tree(new, {".sdd-rebuild/.gitattributes": "x"})
    else:
        write_tree(new, {".sdd-rebuild/lineage.json": '{"tool": "other"}'})
    result = check(sdd_rebuild, new, gen1(tmp_path, sdd_export))

    assert (result.code, result.out["reason"], result.out["rebuild_dir"]) == (3, "rebuild-conflict", "conflict")
    assert result.out["rebuild_conflicts"]


def export_fixture_bytes(name: str) -> bytes:
    return (REPO_ROOT / "tests" / "unit" / "fixtures" / "sdd_export" / name).read_bytes()


@pytest.mark.parametrize("content", [b"not json", b'{"tool": "sdd-rebuild", "schema": 1}', b'{"tool": "sdd-rebuild", "schema": 9}'])
def test_check_rebuild_dir_invalid(sdd_rebuild, tmp_path, sdd_export, content):
    new = make_rebuild_new(tmp_path)
    write_tree(new, {".sdd-rebuild/lineage.json": content})
    result = check(sdd_rebuild, new, gen1(tmp_path, sdd_export))

    assert (result.code, result.out["reason"], result.out["rebuild_dir"]) == (3, "rebuild-conflict", "invalid")


def test_check_empty_rebuild_dir_is_fine(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path)
    (new / ".sdd-rebuild").mkdir()

    assert ok(check(sdd_rebuild, new, gen1(tmp_path, sdd_export)))["rebuild_dir"] == "empty"


def test_check_a_project_rebuilt_already(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path)
    write_tree(new, {".sdd-rebuild/lineage.json": export_fixture_bytes("lineage-gen2.json")})
    result = check(sdd_rebuild, new, gen1(tmp_path, sdd_export))

    assert (result.code, result.out["reason"], result.out["rebuild_dir"]) == (3, "rebuilt", "ours")


@pytest.mark.parametrize(
    "setup, expected",
    [
        ("speckit+old-missing", "speckit-missing"),
        ("old-missing+rebuilt", "old-missing"),
        ("same+rebuilt", "same-project"),
        ("rebuilt+nutrients", "rebuilt"),
        ("rebuild-conflict+nutrients", "rebuild-conflict"),
        ("nutrients+progress", "nutrients-invalid"),
    ],
)
def test_check_reason_priority(sdd_rebuild, tmp_path, sdd_export, setup, expected):
    new = make_rebuild_new(tmp_path)
    old = gen1(tmp_path, sdd_export)
    target = old
    if "speckit" in setup:
        shutil.rmtree(new / ".specify")
    if "old-missing" in setup:
        target = tmp_path / "nowhere"
    if "same" in setup:
        target = new
    if "rebuilt" in setup:
        write_tree(new, {".sdd-rebuild/lineage.json": export_fixture_bytes("lineage-gen2.json")})
    if "rebuild-conflict" in setup:
        write_tree(new, {".sdd-rebuild/x": "x"})
    if "nutrients" in setup:
        write_tree(old, {".sdd-export/nutrients.json": '{"tool": "sdd-export", "schema": 1}'})
    if "progress" in setup:
        write_tree(new, {".specify/sdd-rebuild/progress.json": "broken", ".specify/sdd-rebuild/.gitignore": OWN_GITIGNORE})

    assert check(sdd_rebuild, new, target).out["reason"] == expected


# ------------------------------------------------------- (T014) check, B


def test_check_nutrients_conflict(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    write_tree(old, {".sdd-export/mine.txt": "x"})
    result = check(sdd_rebuild, make_rebuild_new(tmp_path), old)

    assert (result.code, result.out["reason"], result.out["export_dir"]) == (3, "nutrients-conflict", "conflict")
    assert result.out["conflicts"] == [".sdd-export/mine.txt"]
    assert result.out["nutrients"] is None


@pytest.mark.parametrize(
    "content, reason, state",
    [
        (b"\xff\xfe", "nutrients-unreadable", "unreadable"),
        (b'{"tool": "sdd-export", "schema": 1}', "nutrients-invalid", "invalid"),
        (b'{"tool": "sdd-export", "schema": 2}', "nutrients-newer", "newer"),
    ],
)
def test_check_nutrients_that_cannot_be_used(sdd_rebuild, tmp_path, sdd_export, content, reason, state):
    old = gen1(tmp_path, sdd_export)
    write_tree(old, {".sdd-export/nutrients.json": content})
    result = check(sdd_rebuild, make_rebuild_new(tmp_path), old)

    assert (result.code, result.out["reason"], result.out["export_dir"]) == (3, reason, state)
    if state in ("unreadable", "invalid"):
        assert result.out["nutrients_errors"] and set(result.out["nutrients_errors"][0]) == {"check", "path", "detail"}


def test_check_hand_edited_nutrients(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    data = nutrients_of(old)
    data["features"][0]["title"] = "改過的標題"
    (old / ".sdd-export" / "nutrients.json").write_bytes(sdd_export.serialize(data, "nutrients"))
    out = ok(check(sdd_rebuild, make_rebuild_new(tmp_path), old))
    (old / ".sdd-export" / "README.md").unlink()
    unknown = ok(check(sdd_rebuild, make_rebuild_new(tmp_path, name="new2"), old))

    assert out["nutrients_edited"] is True and unknown["nutrients_edited"] is True


@pytest.mark.parametrize(
    "lineage, state",
    [
        ("lineage-gen2.json", "present"),
        ("lineage-gen3.json", "mismatch"),
        (b"not json", "unreadable"),
        (b'{"tool": "sdd-rebuild", "schema": 1}', "invalid"),
        (b'{"tool": "sdd-rebuild", "schema": 5}', "newer"),
        (b'{"tool": "something"}', "conflict"),
    ],
)
def test_check_old_lineage(sdd_rebuild, tmp_path, sdd_export, lineage, state):
    old = gen2(tmp_path, sdd_export, lineage=False)
    write_tree(old, {".sdd-rebuild/lineage.json": export_fixture_bytes(lineage) if isinstance(lineage, str) else lineage})
    out = ok(check(sdd_rebuild, make_rebuild_new(tmp_path), old))

    assert out["old_lineage"] == state
    assert out["needs_old_lineage"] is True
    assert bool(out["old_lineage_errors"]) == (state in ("unreadable", "invalid"))


def test_check_progress_present_unreadable_and_conflict(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    out = ok(check(sdd_rebuild, new))
    assert (out["progress"], out["saved"]["phase"], out["old"]["path"]) == ("present", "deciding", os.path.realpath(old))
    assert out["next"]["step"] == "decide"

    (new / ".specify/sdd-rebuild/progress.json").write_text("{broken")
    unreadable = check(sdd_rebuild, new, old)
    assert (unreadable.code, unreadable.out["reason"], unreadable.out["progress"]) == (3, "progress-unreadable", "unreadable")

    (new / ".specify/sdd-rebuild/notes.txt").write_text("mine")
    conflict = check(sdd_rebuild, new, old)
    assert conflict.out["progress"] == "conflict"


@pytest.mark.parametrize("case", ["gitignore", "file"])
def test_check_progress_conflict_cases(sdd_rebuild, tmp_path, sdd_export, case):
    new = make_rebuild_new(tmp_path)
    if case == "gitignore":
        write_tree(new, {".specify/sdd-rebuild/.gitignore": "*\n"})
    else:
        write_tree(new, {".specify/sdd-rebuild": "x"})

    assert check(sdd_rebuild, new, gen1(tmp_path, sdd_export)).out["progress"] == "conflict"


def test_check_old_mismatch(sdd_rebuild, tmp_path, sdd_export):
    old, new, _ = started(sdd_rebuild, tmp_path, sdd_export)
    other = gen1(tmp_path, sdd_export, name="other")
    result = check(sdd_rebuild, new, other)
    same = check(sdd_rebuild, new, old)

    assert (result.code, result.out["reason"]) == (1, "old-mismatch")
    assert result.out["old"]["path"] == os.path.realpath(other)
    assert result.out["saved"]["old_project"] == os.path.realpath(old)
    assert same.code == 0


def test_check_with_progress_survives_a_vanished_old_project(sdd_rebuild, tmp_path, sdd_export):
    old, new, _ = started(sdd_rebuild, tmp_path, sdd_export)
    shutil.rmtree(old)
    out = ok(check(sdd_rebuild, new))

    assert (out["old"]["state"], out["source_state"], out["source_changed"]) == ("missing", "unavailable", None)
    assert out["saved"] is not None and out["next"]["step"] == "decide"


def test_check_with_progress_and_broken_nutrients_is_not_an_error(sdd_rebuild, tmp_path, sdd_export):
    old, new, _ = started(sdd_rebuild, tmp_path, sdd_export)
    write_tree(old, {".sdd-export/nutrients.json": "broken"})
    out = ok(check(sdd_rebuild, new))

    assert (out["export_dir"], out["source_state"]) == ("unreadable", "unavailable")


def test_check_reports_changed_nutrients_with_a_diff(sdd_rebuild, tmp_path, sdd_export):
    old, new, _ = started(sdd_rebuild, tmp_path, sdd_export)
    out = ok(check(sdd_rebuild, new))
    assert (out["source_state"], out["source_changed"], out["source_diff"]) == (
        "available", {"nutrients": False, "lineage": False}, None)

    data = nutrients_of(old)
    data["features"][0]["title"] = "新標題"
    (old / ".sdd-export" / "nutrients.json").write_bytes(sdd_export.serialize(data, "nutrients"))
    write_tree(old, {".sdd-rebuild/lineage.json": "x"})
    out = ok(check(sdd_rebuild, new))

    assert out["source_changed"] == {"nutrients": True, "lineage": True}
    assert out["source_diff"]["changed"][0]["id"] == "deploy"


def test_check_crlf_nutrients_are_not_a_change(sdd_rebuild, tmp_path, sdd_export):
    old, new, _ = started(sdd_rebuild, tmp_path, sdd_export)
    path = old / ".sdd-export" / "nutrients.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    assert ok(check(sdd_rebuild, new))["source_changed"] == {"nutrients": False, "lineage": False}


def test_check_reports_what_changed_in_the_new_project(sdd_rebuild, tmp_path, sdd_export):
    old, new, _ = started(sdd_rebuild, tmp_path, sdd_export)
    write_tree(new, {"specs/001-mine/spec.md": "# mine\n", ".specify/memory/constitution.md": WRITTEN_CONSTITUTION})
    git_commit_all(new)

    assert ok(check(sdd_rebuild, new))["changed"] == ["constitution", "specs", "head"]


def next_of(module, new):
    return ok(check(module, new))["next"]


def test_check_next_step_through_the_whole_run(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    assert next_of(sdd_rebuild, new)["step"] == "decide"
    progress = confirm(sdd_rebuild, new, progress)
    assert next_of(sdd_rebuild, new)["step"] == "constitution"
    simulate_constitution(new)
    progress["generation"]["constitution"] = "written"
    ok(save(sdd_rebuild, new, progress))
    assert next_of(sdd_rebuild, new)["step"] == "review-constitution"
    progress["generation"]["constitution"] = "reviewed"
    ok(save(sdd_rebuild, new, progress))
    assert next_of(sdd_rebuild, new) == {"step": "specify", "feature": "deploy", "candidates": []}
    folder = simulate_specify(new, "deploy")
    assert next_of(sdd_rebuild, new) == {"step": "claim", "feature": "deploy", "candidates": [folder]}
    ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))
    assert next_of(sdd_rebuild, new) == {"step": "review", "feature": "deploy", "candidates": []}
    progress["target"]["features"][0].update(spec_dir=folder, reviewed=True)
    ok(save(sdd_rebuild, new, progress))
    assert next_of(sdd_rebuild, new)["feature"] == "status"
    folder2 = simulate_specify(new, "status")
    ok(run_rebuild(sdd_rebuild, new, "claim", "status"))
    progress["target"]["features"][1].update(spec_dir=folder2, reviewed=True)
    ok(save(sdd_rebuild, new, progress))
    assert next_of(sdd_rebuild, new)["step"] == "verify"
    ok(run_rebuild(sdd_rebuild, new, "lineage"))
    write_tree(new, {".specify/feature.json": '{"feature_directory": "specs/002-status"}'})
    assert next_of(sdd_rebuild, new)["step"] == "focus"
    ok(run_rebuild(sdd_rebuild, new, "focus"))
    assert next_of(sdd_rebuild, new)["step"] == "clear"


def test_check_next_is_clear_when_every_feature_has_an_existing_spec(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, specs={"001-deploy": "# d\n", "002-status": "# s\n"})
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    for feature, folder in zip(progress["target"]["features"], ("specs/001-deploy", "specs/002-status")):
        feature.update(existing_spec=folder, reviewed=True)
    progress["constitution"]["action"] = "keep"
    progress["generation"]["constitution"] = "not-needed"
    ok(save(sdd_rebuild, new, progress))
    confirm(sdd_rebuild, new, progress)
    assert next_of(sdd_rebuild, new)["step"] == "verify"
    ok(run_rebuild(sdd_rebuild, new, "lineage"))

    assert next_of(sdd_rebuild, new) == {"step": "clear", "feature": None, "candidates": []}


def test_check_is_read_only(sdd_rebuild, tmp_path, sdd_export):
    old, new, _ = started(sdd_rebuild, tmp_path, sdd_export)
    before_old, before_new = tree_snapshot(old), tree_snapshot(new)
    ok(check(sdd_rebuild, new))
    run_rebuild(sdd_rebuild, new, "check", "--old", str(tmp_path / "nowhere"))

    assert tree_snapshot(old) == before_old and tree_snapshot(new) == before_new


def test_check_through_uv_matches_main(sdd_rebuild, tmp_path, sdd_export, export_env):
    from conftest import real_run_env, run_rebuild_real

    skills = copy_skills(tmp_path)
    old = gen1(tmp_path, sdd_export)
    new = make_rebuild_new(tmp_path)
    before = tree_snapshot(new)
    done = run_rebuild_real(new, real_run_env(export_env), "check", "--old", str(old),
                            script=skills / "sdd-rebuild" / "scripts" / "sdd_rebuild.py")

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.decode("utf-8")) == ok(check(sdd_rebuild, new, old))
    assert tree_snapshot(new) == before
    assert not (new / ".venv").exists() and not (new / "uv.lock").exists()


# ---------------------------------------------------------- (T015) save


def test_first_save_writes_only_the_own_folder(sdd_rebuild, tmp_path, sdd_export):
    old = gen1(tmp_path, sdd_export)
    new = make_rebuild_new(tmp_path)
    before_old, before_new = tree_snapshot(old), tree_snapshot(new)
    progress = keep_all_progress(os.path.realpath(old), nutrients_of(old), "not-needed")
    out = ok(save(sdd_rebuild, new, progress))

    assert out == {"saved": ".specify/sdd-rebuild/progress.json", "phase": "deciding", "baseline": False,
                   "snapshot": "created"}
    changes = tree_changes(before_new, tree_snapshot(new))
    assert changes == {"added": [".specify/sdd-rebuild", ".specify/sdd-rebuild/.gitignore",
                                 ".specify/sdd-rebuild/progress.json"], "removed": [], "changed": []}
    assert (new / ".specify/sdd-rebuild/.gitignore").read_bytes() == OWN_GITIGNORE
    assert tree_snapshot(old) == before_old


def test_saved_progress_holds_the_snapshot_and_script_fields(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    data = saved(new)
    raw = (old / ".sdd-export" / "nutrients.json").read_bytes()

    assert list(data) == ["schema", "tool", "old_project", "language", "phase", "stage", "source", "old_lineage",
                          "constitution", "target", "discards", "pending_decided", "adjustments", "deferred",
                          "for_plan", "generation", "rebuilt_at", "saved_at", "fingerprint", "baseline",
                          "lineage_written"]
    assert data["source"] == {"nutrients": nutrients_of(old), "nutrients_sha256": sdd_export.content_hash(raw),
                              "lineage_state": "none", "lineage": None, "lineage_sha256": None}
    assert (data["saved_at"], data["rebuilt_at"], data["baseline"], data["lineage_written"]) == (NOW, None, None, None)
    assert set(data["fingerprint"]) == {"constitution", "specs", "head"}
    raw_progress = (new / ".specify/sdd-rebuild/progress.json").read_bytes()
    assert raw_progress == json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def test_save_ignores_script_fields_sent_by_claude(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    progress.update(source={"nutrients": {}}, saved_at="x", fingerprint={}, baseline={"x": 1}, rebuilt_at="1999-01-01",
                    lineage_written="abc")
    ok(save(sdd_rebuild, new, progress))
    data = saved(new)

    assert data["source"]["nutrients"] == nutrients_of(old)
    assert (data["saved_at"], data["baseline"], data["rebuilt_at"], data["lineage_written"]) == (NOW, None, None, None)


def test_later_saves_keep_the_snapshot(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    first = saved(new)["source"]
    data = nutrients_of(old)
    data["features"][0]["title"] = "新標題"
    (old / ".sdd-export" / "nutrients.json").write_bytes(sdd_export.serialize(data, "nutrients"))
    out = ok(save(sdd_rebuild, new, progress))

    assert out["snapshot"] == "kept" and saved(new)["source"] == first


def test_refresh_source_takes_the_current_nutrients(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    data = nutrients_of(old)
    data["features"][0]["title"] = "新標題"
    (old / ".sdd-export" / "nutrients.json").write_bytes(sdd_export.serialize(data, "nutrients"))
    out = ok(save(sdd_rebuild, new, progress, "--refresh-source"))

    assert out["snapshot"] == "refreshed"
    assert saved(new)["source"]["nutrients"]["features"][0]["title"] == "新標題"


def test_refresh_source_is_refused_once_confirmed(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    before = tree_snapshot(new)
    result = save(sdd_rebuild, new, progress, "--refresh-source")

    assert (result.code, result.out["reason"]) == (1, "frozen")
    assert tree_snapshot(new) == before


@pytest.mark.parametrize("flags", [(), ("--refresh-source",)])
def test_save_needs_usable_nutrients_for_the_snapshot(sdd_rebuild, tmp_path, sdd_export, flags):
    if flags:
        old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    else:
        old, new = gen1(tmp_path, sdd_export), make_rebuild_new(tmp_path)
        progress = keep_all_progress(os.path.realpath(old), nutrients_of(old), "not-needed")
    write_tree(old, {".sdd-export/nutrients.json": "broken"})
    before = tree_snapshot(new)
    result = save(sdd_rebuild, new, progress, *flags)

    assert (result.code, result.out["reason"]) == (1, "source")
    assert tree_snapshot(new) == before


def test_save_refuses_an_old_project_that_is_the_new_one(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path)
    place_export(sdd_export, new, export_fixture("nutrients.json"))
    progress = keep_all_progress(os.path.realpath(new), export_fixture("nutrients.json"), "skipped")

    assert save(sdd_rebuild, new, progress).out["reason"] == "source"


def invalid_at(module, new, progress, *flags):
    result = save(module, new, progress, *flags)
    assert (result.code, result.out["reason"]) == (1, "invalid"), result.out
    return result.out["path"]


@pytest.mark.parametrize(
    "change, path",
    [
        (lambda p: p.pop("discards"), "discards"),
        (lambda p: p.update(plan="x"), "plan"),
        (lambda p: p.update(tasks=[]), "tasks"),
        (lambda p: p.update(schema=2), "schema"),
        (lambda p: p.update(tool="sdd-grill"), "tool"),
        (lambda p: p.update(phase="done"), "phase"),
        (lambda p: p.update(stage="other"), "stage"),
        (lambda p: p.update(language=""), "language"),
        (lambda p: p.update(old_lineage="maybe"), "old_lineage"),
        (lambda p: p["constitution"].update(action="rewrite"), "constitution.action"),
        (lambda p: p["target"]["principles"][0].update(basis="copy"), "target.principles[0].basis"),
        (lambda p: p["target"]["principles"][0].update(title=""), "target.principles[0].title"),
        (lambda p: p["target"]["features"][0].update(code="x"), "target.features[0].code"),
        (lambda p: p["target"]["features"][0]["requirements"][0].update(kind="wish"),
         "target.features[0].requirements[0].kind"),
        (lambda p: p["target"]["principles"][0].update(id="Bad_Id"), "target.principles[0].id"),
        (lambda p: p["target"]["features"][1]["requirements"][0].update(id="deploy-no-overwrite"),
         "target.features[1].requirements[0].id"),
        (lambda p: p["target"]["features"][0].update(depends_on=["status"]), "target.features[0].depends_on[0]"),
        (lambda p: p["target"]["principles"][0].update(basis="derived"), "target.principles[0].from"),
        (lambda p: p["target"]["principles"][0].update(**{"from": ["x"]}), "target.principles[0].from"),
        (lambda p: p["target"]["principles"].append({"id": "n", "basis": "new", "from": [], "title": None, "text": "x"}),
         "target.principles[1].title"),
        (lambda p: p["target"]["features"][0].update(requirements=[]), "target.features[0].requirements"),
        (lambda p: p["target"]["features"][0]["requirements"][0].update(text="a\n```\ncode\n```"),
         "target.features[0].requirements[0].text"),
        (lambda p: p["target"]["features"][0].update(existing_spec="other/x"), "target.features[0].existing_spec"),
        (lambda p: p["target"]["features"][0].update(spec_dir="specs/001-x"), "target.features[0].spec_dir"),
        (lambda p: p["target"]["features"][0].update(reviewed=True), "target.features[0].reviewed"),
        (lambda p: p["discards"].append({"id": "x", "text": "", "reason": None}), "discards[0].text"),
        (lambda p: p["adjustments"].append({"lesson": "atomic-write", "change": "x", "adopted": "yes"}),
         "adjustments[0].adopted"),
        (lambda p: p["adjustments"].append({"lesson": "nothing", "change": "x", "adopted": None}),
         "adjustments[0].lesson"),
        (lambda p: p["deferred"].append({"item": "x", "reason": "y", "feature": "nothing"}), "deferred[0].feature"),
        (lambda p: p["for_plan"].append({"item": "x"}), "for_plan[0].feature"),
        (lambda p: p["generation"].update(constitution="written"), "generation.constitution"),
        (lambda p: p.update(old_project="relative/path"), "old_project"),
    ],
)
def test_save_rule_violations(sdd_rebuild, tmp_path, sdd_export, change, path):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    before = tree_snapshot(new)
    change(progress)

    assert invalid_at(sdd_rebuild, new, progress) == path
    assert tree_snapshot(new) == before


def test_save_rejects_text_that_is_not_json(sdd_rebuild, tmp_path):
    new = make_rebuild_new(tmp_path)
    result = run_rebuild(sdd_rebuild, new, "save", stdin="not json")

    assert (result.code, result.out["reason"]) == (1, "invalid")
    assert not (new / ".specify/sdd-rebuild").exists()


def test_save_keeps_the_old_project(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    other = gen1(tmp_path, sdd_export, name="other")
    progress["old_project"] = os.path.realpath(other)

    assert invalid_at(sdd_rebuild, new, progress) == "old_project"


@pytest.mark.parametrize(
    "lineage_setup, generation, allowed",
    [
        ("present", 2, "used"),
        ("none", 1, "not-needed"),
        ("none", 2, "skipped"),
        ("mismatch", 2, "skipped"),
        ("unreadable", 2, "skipped"),
        ("invalid", 2, "skipped"),
        ("newer", 2, "skipped"),
        ("conflict", 2, "skipped"),
    ],
)
def test_save_old_lineage_must_match_the_snapshot(sdd_rebuild, tmp_path, sdd_export, lineage_setup, generation, allowed):
    if generation == 1:
        old = gen1(tmp_path, sdd_export)
    else:
        old = gen2(tmp_path, sdd_export, lineage=False)
        content = {
            "present": export_fixture_bytes("lineage-gen2.json"), "none": None,
            "mismatch": export_fixture_bytes("lineage-gen3.json"), "unreadable": b"x",
            "invalid": b'{"tool": "sdd-rebuild", "schema": 1}', "newer": b'{"tool": "sdd-rebuild", "schema": 3}',
            "conflict": b'{"tool": "other"}',
        }[lineage_setup]
        if content is not None:
            write_tree(old, {".sdd-rebuild/lineage.json": content})
    new = make_rebuild_new(tmp_path)
    for value in ("used", "not-needed", "skipped"):
        progress = keep_all_progress(os.path.realpath(old), nutrients_of(old), value)
        result = save(sdd_rebuild, new, progress)
        if value == allowed:
            assert result.code == 0, result.out
            assert saved(new)["source"]["lineage_state"] == lineage_setup
        else:
            assert (result.out["reason"], result.out["path"]) == ("invalid", "old_lineage"), value


def test_save_secret(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    token = "ghp_" + "a1B2" * 6
    progress["deferred"].append({"item": f"token = {token}", "reason": "later", "feature": None})
    result = save(sdd_rebuild, new, progress)

    assert (result.code, result.out["reason"], result.out["path"]) == (1, "secret", "deferred[0].item")
    assert token not in result.raw.decode("utf-8") and token not in result.err


def test_confirm_records_baseline_and_rebuilt_at(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    progress.update(phase="confirmed", stage="summary")
    out = ok(save(sdd_rebuild, new, progress))
    data = saved(new)

    assert (out["phase"], out["baseline"]) == ("confirmed", True)
    assert data["rebuilt_at"] == TODAY
    assert data["baseline"] == {"constitution": None, "specs": {},
                                "confirmed_counts": {"governance": 0, "deferred": 0, "for_plan": 0}}
    assert ok(save(sdd_rebuild, new, progress))["baseline"] is False  # kept, not recorded again


def test_confirm_needs_language_and_decided_adjustments_and_passing_checks(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    for change, path in (
        (dict(language=None), "language"),
        (dict(adjustments=[{"lesson": "atomic-write", "change": "x", "adopted": None}]), "adjustments[0].adopted"),
        (dict(stage="lessons"), "stage"),
    ):
        candidate = {**copy.deepcopy(progress), "phase": "confirmed", "stage": "summary", **change}
        assert invalid_at(sdd_rebuild, new, candidate) == path
    candidate = {**copy.deepcopy(progress), "phase": "confirmed", "stage": "summary"}
    candidate["target"]["lessons"] = []
    result = save(sdd_rebuild, new, candidate)
    assert (result.out["reason"], {e["check"] for e in result.out["errors"]}) == ("invalid", {"unaccounted"})


def test_back_to_deciding_before_anything_was_generated(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    progress.update(phase="deciding", stage="items")
    out = ok(save(sdd_rebuild, new, progress))

    assert out["phase"] == "deciding"
    assert (saved(new)["baseline"], saved(new)["rebuilt_at"]) == (None, None)


@pytest.mark.parametrize("generated", ["constitution", "spec"])
def test_no_going_back_once_something_was_generated(sdd_rebuild, tmp_path, sdd_export, generated):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    if generated == "constitution":
        simulate_constitution(new)
        progress["generation"]["constitution"] = "written"
        ok(save(sdd_rebuild, new, progress))
    else:
        simulate_specify(new, "deploy")
        progress["target"]["features"][0]["spec_dir"] = ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))["spec_dir"]
    before = tree_snapshot(new)
    progress.update(phase="deciding", stage="items")
    if generated == "constitution":
        progress["generation"]["constitution"] = "pending"
    else:
        progress["target"]["features"][0]["spec_dir"] = None

    assert save(sdd_rebuild, new, progress).out["reason"] == "frozen"
    assert tree_snapshot(new) == before


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p["target"]["principles"][0].update(title="改了"),
        lambda p: p.update(discards=[{"id": "json-format", "text": None, "reason": None}]),
        lambda p: p.update(language="en"),
        lambda p: p["constitution"].update(action="amend"),
        lambda p: p.update(pending_decided=["x"]),
        lambda p: p.update(adjustments=[{"lesson": "atomic-write", "change": "x", "adopted": True}]),
        lambda p: p["constitution"].update(governance=[]),
        lambda p: p.update(deferred=[]),
        lambda p: p["deferred"][0].update(item="changed"),
    ],
)
def test_confirmed_content_is_frozen(sdd_rebuild, tmp_path, sdd_export, change):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    progress["constitution"]["governance"] = ["規則一"]
    progress["deferred"] = [{"item": "延後", "reason": "之後", "feature": None}]
    ok(save(sdd_rebuild, new, progress))
    progress = confirm(sdd_rebuild, new, progress)
    change(progress)

    assert save(sdd_rebuild, new, progress).out["reason"] == "frozen"


def test_confirmed_append_only_fields_may_grow(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    progress["constitution"]["governance"].append("維護者同意保留的規則")
    progress["deferred"].append({"item": "澄清後延後的事", "reason": "之後", "feature": "deploy"})
    progress["for_plan"].append({"item": "選用的工具", "feature": None})
    ok(save(sdd_rebuild, new, progress))

    assert saved(new)["constitution"]["governance"] == ["維護者同意保留的規則"]


def test_confirmed_generation_and_reviewed_only_move_forward(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    simulate_constitution(new)
    progress["generation"]["constitution"] = "reviewed"
    ok(save(sdd_rebuild, new, progress))
    progress["generation"]["constitution"] = "written"
    assert save(sdd_rebuild, new, progress).out["reason"] == "frozen"
    progress["generation"]["constitution"] = "reviewed"
    simulate_specify(new, "deploy")
    progress["target"]["features"][0]["spec_dir"] = ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))["spec_dir"]
    progress["target"]["features"][0]["reviewed"] = True
    ok(save(sdd_rebuild, new, progress))
    progress["target"]["features"][0]["reviewed"] = False
    assert save(sdd_rebuild, new, progress).out["reason"] == "frozen"


def test_spec_dir_is_written_by_claim_only(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    simulate_specify(new, "deploy")
    ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))
    progress["target"]["features"][0]["spec_dir"] = None  # not carried over from claim

    assert invalid_at(sdd_rebuild, new, progress) == "target.features[0].spec_dir"
    progress["target"]["features"][0]["spec_dir"] = "specs/009-elsewhere"
    assert invalid_at(sdd_rebuild, new, progress) == "target.features[0].spec_dir"


def test_reviewed_needs_a_spec_dir(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    progress["target"]["features"][0]["reviewed"] = True

    assert invalid_at(sdd_rebuild, new, progress) == "target.features[0].reviewed"


def test_save_after_the_lineage_is_written(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    progress = generate_all(sdd_rebuild, new, progress)
    ok(run_rebuild(sdd_rebuild, new, "lineage"))

    assert save(sdd_rebuild, new, progress).out["reason"] == "finished"


def test_save_refuses_a_folder_with_strangers(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    write_tree(new, {".specify/sdd-rebuild/mine.txt": "x"})
    before = tree_snapshot(new)

    assert save(sdd_rebuild, new, progress).out["reason"] == "conflict"
    assert tree_snapshot(new) == before


def test_save_os_error_leaves_the_progress_as_it_was(sdd_rebuild, sdd_grill, tmp_path, sdd_export, monkeypatch):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    before = tree_snapshot(new)
    real_replace = os.replace

    def failing_replace(source, target):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(os, "replace", failing_replace)
    progress["stage"] = "new"
    result = save(sdd_rebuild, new, progress)
    monkeypatch.setattr(os, "replace", real_replace)

    assert (result.code, result.out["reason"]) == (1, "os-error")
    assert tree_snapshot(new) == before


def test_existing_spec_feature_spec_dir_and_reviewed(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, specs={"001-deploy": "# d\n"})
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    progress["target"]["features"][0].update(existing_spec="specs/001-deploy", reviewed=False)
    ok(save(sdd_rebuild, new, progress))
    assert saved(new)["target"]["features"][0]["reviewed"] is True
    assert saved(new)["target"]["features"][0]["spec_dir"] is None
    progress = confirm(sdd_rebuild, new, progress)

    assert saved(new)["target"]["features"][0]["spec_dir"] == "specs/001-deploy"
    progress["target"]["features"][0]["spec_dir"] = "specs/001-deploy"
    ok(save(sdd_rebuild, new, progress))


# ------------------------------------------------------- (T016) preview


def test_preview_keep_all(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    before_old, before_new = tree_snapshot(old), tree_snapshot(new)
    out = ok(run_rebuild(sdd_rebuild, new, "preview"))

    assert list(out) == ["ok", "errors", "generation", "lineage", "summary", "counts"]
    assert (out["ok"], out["errors"], out["generation"]) == (True, [], 2)
    assert list(out["summary"]) == ["kept", "modified", "merged", "split", "added", "discarded", "pending_decided",
                                    "adjustments", "order"]
    summary = out["summary"]
    assert [e["id"] for e in summary["kept"]] == ["cross-platform", "deploy", "deploy-no-overwrite", "deploy-symlink",
                                                  "status", "status-list", "atomic-write", "json-format"]
    assert summary["kept"][1] == {"section": "features", "id": "deploy", "title": nutrients_of(old)["features"][0]["title"]}
    assert all(summary[key] == [] for key in ("modified", "merged", "split", "added", "discarded"))
    assert summary["order"] == [
        {"id": "deploy", "title": nutrients_of(old)["features"][0]["title"], "depends_on": [], "existing_spec": None},
        {"id": "status", "title": nutrients_of(old)["features"][1]["title"], "depends_on": ["deploy"], "existing_spec": None},
    ]
    assert out["counts"] == {"principles": 1, "features": 2, "requirements": 3, "lessons": 2, "discarded": 0}
    assert out["lineage"]["rebuilt_at"] is None
    assert [f["spec_dir"] for f in out["lineage"]["features"]] == [None, None]
    assert tree_snapshot(old) == before_old and tree_snapshot(new) == before_new


def test_preview_when_the_decisions_are_incomplete(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    progress["target"]["lessons"] = progress["target"]["lessons"][:1]
    ok(save(sdd_rebuild, new, progress))
    before = tree_snapshot(new)
    result = run_rebuild(sdd_rebuild, new, "preview")

    assert (result.code, result.out["reason"], result.out["error"]) == (1, "invalid", PREVIEW_ERROR)
    assert [e["check"] for e in result.out["errors"]] == ["unaccounted"]
    assert result.out["summary"]["kept"] and result.out["counts"]["lessons"] == 1
    assert tree_snapshot(new) == before


def test_preview_works_on_confirmed_progress(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    out = ok(run_rebuild(sdd_rebuild, new, "preview"))

    assert out["lineage"]["rebuilt_at"] == TODAY


def test_preview_without_progress(sdd_rebuild, tmp_path):
    result = run_rebuild(sdd_rebuild, make_rebuild_new(tmp_path), "preview")

    assert (result.code, result.out["reason"]) == (1, "no-progress")


# --------------------------------------------------------- (T017) claim


def test_claim_records_the_new_spec(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    folder = simulate_specify(new, "deploy")
    before = tree_snapshot(new)
    out = ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))

    assert out == {"feature": "deploy", "spec_dir": folder, "feature_directory": folder, "candidates": [folder],
                   "incomplete": []}
    assert saved(new)["target"]["features"][0]["spec_dir"] == folder
    assert tree_changes(before, tree_snapshot(new))["changed"] == [".specify/sdd-rebuild/progress.json"]
    assert tree_changes(before, tree_snapshot(new))["added"] == []


def test_claim_without_a_new_spec(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    (new / "specs" / "001-half").mkdir(parents=True)
    before = tree_snapshot(new)
    result = run_rebuild(sdd_rebuild, new, "claim", "deploy")

    assert (result.code, result.out["reason"]) == (1, "none")
    assert (result.out["candidates"], result.out["incomplete"]) == ([], ["specs/001-half"])
    assert tree_snapshot(new) == before


def test_claim_ambiguous_and_dir(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    write_tree(new, {"specs/001-mine/spec.md": "# mine\n"})
    folder = simulate_specify(new, "deploy")
    result = run_rebuild(sdd_rebuild, new, "claim", "deploy")

    assert (result.code, result.out["reason"], result.out["candidates"]) == (1, "ambiguous", ["specs/001-mine", folder])
    assert saved(new)["target"]["features"][0]["spec_dir"] is None
    bad = run_rebuild(sdd_rebuild, new, "claim", "deploy", "--dir", "specs/009-none")
    assert bad.out["reason"] == "usage"
    out = ok(run_rebuild(sdd_rebuild, new, "claim", "deploy", "--dir", folder))
    assert out["spec_dir"] == folder and saved(new)["target"]["features"][0]["spec_dir"] == folder


def test_claim_mismatch(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    simulate_specify(new, "deploy")
    write_tree(new, {".specify/feature.json": '{"feature_directory": "specs/elsewhere"}'})
    result = run_rebuild(sdd_rebuild, new, "claim", "deploy")

    assert (result.code, result.out["reason"], result.out["feature_directory"]) == (1, "mismatch", "specs/elsewhere")


@pytest.mark.parametrize("case", ["second-first", "unknown", "already", "existing"])
def test_claim_not_next(sdd_rebuild, tmp_path, sdd_export, case):
    new = make_rebuild_new(tmp_path, specs={"001-deploy": "# d\n"}) if case == "existing" else None
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    if case == "existing":
        progress["target"]["features"][0]["existing_spec"] = "specs/001-deploy"
        ok(save(sdd_rebuild, new, progress))
    progress = confirm(sdd_rebuild, new, progress)
    simulate_specify(new, "x")
    feature = {"second-first": "status", "unknown": "nothing", "already": "deploy", "existing": "deploy"}[case]
    if case == "already":
        ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))
        simulate_specify(new, "y")
    before = tree_snapshot(new)
    result = run_rebuild(sdd_rebuild, new, "claim", feature)

    assert (result.code, result.out["reason"]) == (1, "not-next")
    assert tree_snapshot(new) == before


def test_claim_needs_confirmed_progress(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path)
    assert run_rebuild(sdd_rebuild, new, "claim", "deploy").out["reason"] == "no-progress"
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    assert run_rebuild(sdd_rebuild, new, "claim", "deploy").out["reason"] == "no-progress"


def test_claim_ignores_baseline_specs_and_claimed_ones(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, specs={"001-before": "# b\n"})
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    progress = confirm(sdd_rebuild, new, progress)
    first = simulate_specify(new, "deploy")
    ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))
    second = simulate_specify(new, "status")
    out = ok(run_rebuild(sdd_rebuild, new, "claim", "status"))

    assert out["candidates"] == [second] and first != second


def test_claim_conflict(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    simulate_specify(new, "deploy")
    write_tree(new, {".specify/sdd-rebuild/mine.txt": "x"})

    assert run_rebuild(sdd_rebuild, new, "claim", "deploy").out["reason"] == "conflict"


# -------------------------------------------------------- (T018) verify


def verify(module, new):
    return run_rebuild(module, new, "verify")


def test_verify_ok(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    generate_all(sdd_rebuild, new, progress)
    before = tree_snapshot(new)
    out = ok(verify(sdd_rebuild, new))

    assert list(out) == ["ok", "failures", "constitution", "specs", "unexpected"]
    assert (out["ok"], out["failures"], out["constitution"], out["unexpected"]) == (True, [], "written", [])
    assert out["specs"] == [
        {"feature": "deploy", "dir": "specs/001-deploy", "depends_on": [], "existing": False},
        {"feature": "status", "dir": "specs/002-status", "depends_on": ["specs/001-deploy"], "existing": False},
    ]
    assert tree_snapshot(new) == before


def test_verify_with_an_existing_spec(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, specs={"001-deploy": "# d\n"})
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    progress["target"]["features"][0]["existing_spec"] = "specs/001-deploy"
    ok(save(sdd_rebuild, new, progress))
    progress = confirm(sdd_rebuild, new, progress)
    progress["target"]["features"][0]["spec_dir"] = "specs/001-deploy"
    progress = generate_all(sdd_rebuild, new, progress)
    out = ok(verify(sdd_rebuild, new))

    assert out["specs"] == [
        {"feature": "deploy", "dir": "specs/001-deploy", "depends_on": [], "existing": True},
        {"feature": "status", "dir": "specs/002-status", "depends_on": ["specs/001-deploy"], "existing": False},
    ]
    shutil.rmtree(new / "specs" / "001-deploy")
    result = verify(sdd_rebuild, new)
    assert (result.code, result.out["reason"]) == (1, "mismatch-documents")
    assert "existing-spec-missing" in [f["check"] for f in result.out["failures"]]


def failures(module, new) -> list[str]:
    result = verify(module, new)
    assert result.code == 1 and result.out["reason"] == "mismatch-documents"
    return [f["check"] for f in result.out["failures"]]


def test_verify_failures_from_sdd_grill(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, specs={"001-before": "# b\n"})
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export, new=new)
    assert "constitution-not-written" in failures(sdd_rebuild, new)
    assert "spec-missing" in failures(sdd_rebuild, new)
    progress = generate_all(sdd_rebuild, new, progress)
    assert ok(verify(sdd_rebuild, new))["ok"] is True

    write_tree(new, {"specs/001-before/spec.md": "# changed\n"})
    assert "existing-spec-changed" in failures(sdd_rebuild, new)
    write_tree(new, {"specs/001-before/spec.md": "# b\n"})
    (new / "specs" / "002-deploy" / "spec.md").unlink()
    assert "spec-missing" in failures(sdd_rebuild, new)


def test_verify_order_and_dependency_order(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    simulate_constitution(new)
    progress["generation"]["constitution"] = "reviewed"
    ok(save(sdd_rebuild, new, progress))
    # the maintainer's own spec slipped in between, and the first feature got a later number
    write_tree(new, {"specs/005-deploy/spec.md": "# d\n", ".specify/feature.json": '{"feature_directory": "specs/005-deploy"}'})
    ok(run_rebuild(sdd_rebuild, new, "claim", "deploy"))
    write_tree(new, {"specs/003-status/spec.md": "# s\n", ".specify/feature.json": '{"feature_directory": "specs/003-status"}'})
    ok(run_rebuild(sdd_rebuild, new, "claim", "status"))
    progress["target"]["features"][0].update(spec_dir="specs/005-deploy", reviewed=True)
    progress["target"]["features"][1].update(spec_dir="specs/003-status", reviewed=True)
    ok(save(sdd_rebuild, new, progress))

    assert {"order", "dependency-order"} <= set(failures(sdd_rebuild, new))


def test_verify_constitution_changed_and_spec_not_new(sdd_rebuild, sdd_grill, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, constitution=WRITTEN_CONSTITUTION, specs={"001-old": "# o\n"})
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    progress["constitution"]["action"] = "keep"
    progress["generation"]["constitution"] = "not-needed"
    ok(save(sdd_rebuild, new, progress))
    progress = confirm(sdd_rebuild, new, progress)
    progress = generate_all(sdd_rebuild, new, progress)
    write_tree(new, {".specify/memory/constitution.md": WRITTEN_CONSTITUTION + "more\n"})
    assert "constitution-changed" in failures(sdd_rebuild, new)
    # spec-not-new comes from sdd-grill's rule; the progress points a feature at a baseline spec by hand
    data = saved(new)
    data["target"]["features"][0]["spec_dir"] = "specs/001-old"
    write_tree(new, {".specify/memory/constitution.md": WRITTEN_CONSTITUTION,
                     ".specify/sdd-rebuild/progress.json": json.dumps(data, ensure_ascii=False)})
    assert "spec-not-new" in failures(sdd_rebuild, new)


def test_verify_not_reviewed(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    simulate_constitution(new)
    progress["generation"]["constitution"] = "written"
    ok(save(sdd_rebuild, new, progress))
    for feature in progress["target"]["features"]:
        simulate_specify(new, feature["id"])
        feature["spec_dir"] = ok(run_rebuild(sdd_rebuild, new, "claim", feature["id"]))["spec_dir"]
    ok(save(sdd_rebuild, new, progress))
    result = verify(sdd_rebuild, new)

    assert [f["check"] for f in result.out["failures"]].count("not-reviewed") == 3


def test_verify_lists_unexpected_folders_without_failing(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    generate_all(sdd_rebuild, new, progress)
    write_tree(new, {"specs/009-mine/spec.md": "# m\n"})
    out = ok(verify(sdd_rebuild, new))

    assert out["unexpected"] == ["specs/009-mine"]


def test_verify_needs_confirmed_progress(sdd_rebuild, tmp_path, sdd_export):
    assert verify(sdd_rebuild, make_rebuild_new(tmp_path, name="empty")).out["reason"] == "no-progress"
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    assert verify(sdd_rebuild, new).out["reason"] == "no-progress"


# ------------------------------------------------------- (T019) lineage


def ready(module, tmp_path, sdd_export, **kwargs):
    old, new, progress = confirmed(module, tmp_path, sdd_export, **kwargs)
    return old, new, generate_all(module, new, progress)


def test_lineage_writes_the_lineage(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    before_old, before_new = tree_snapshot(old), tree_snapshot(new)
    out = ok(run_rebuild(sdd_rebuild, new, "lineage"))

    assert out == {"written": [".sdd-rebuild/lineage.json", ".sdd-rebuild/.gitattributes"], "unchanged": False,
                   "lineage": ".sdd-rebuild/lineage.json", "generation": 2,
                   "counts": {"principles": 1, "features": 2, "requirements": 3, "lessons": 2, "discarded": 0}}
    raw = (new / ".sdd-rebuild" / "lineage.json").read_bytes()
    state, data, problems = sdd_export.load_lineage(new / ".sdd-rebuild" / "lineage.json")
    assert (state, problems) == ("present", [])
    assert raw == sdd_export.serialize(data, "lineage")
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    assert (new / ".sdd-rebuild" / ".gitattributes").read_bytes() == LINEAGE_GITATTRIBUTES
    assert saved(new)["lineage_written"] == sdd_export.content_hash(raw)
    changes = tree_changes(before_new, tree_snapshot(new))
    assert changes["added"] == [".sdd-rebuild", ".sdd-rebuild/.gitattributes", ".sdd-rebuild/lineage.json"]
    assert changes["changed"] == [".specify/sdd-rebuild/progress.json"] and changes["removed"] == []
    assert tree_snapshot(old) == before_old
    assert [f["spec_dir"] for f in data["features"]] == ["specs/001-deploy", "specs/002-status"]
    assert data["rebuilt_at"] == TODAY


def test_lineage_keeps_hand_edited_gitattributes(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    ok(run_rebuild(sdd_rebuild, new, "lineage"))
    write_tree(new, {".sdd-rebuild/.gitattributes": "mine\n"})
    out = ok(run_rebuild(sdd_rebuild, new, "lineage"))

    assert (out["written"], out["unchanged"]) == ([], True)
    assert (new / ".sdd-rebuild/.gitattributes").read_text() == "mine\n"


def test_lineage_is_idempotent_after_an_interruption(sdd_rebuild, tmp_path, sdd_export, monkeypatch):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    real = sdd_rebuild.record_lineage_written

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(sdd_rebuild, "record_lineage_written", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_rebuild(sdd_rebuild, new, "lineage")
    monkeypatch.setattr(sdd_rebuild, "record_lineage_written", real)
    assert saved(new)["lineage_written"] is None
    path = new / ".sdd-rebuild" / "lineage.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    out = ok(run_rebuild(sdd_rebuild, new, "lineage"))

    assert (out["unchanged"], out["written"]) == (True, [])
    assert saved(new)["lineage_written"] == sdd_export.content_hash(path.read_bytes())


def test_lineage_refuses_a_different_existing_lineage(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    ok(run_rebuild(sdd_rebuild, new, "lineage"))
    data = json.loads((new / ".sdd-rebuild/lineage.json").read_bytes())
    data["features"][0]["title"] = "別的"
    (new / ".sdd-rebuild/lineage.json").write_bytes(sdd_export.serialize(data, "lineage"))
    progress_data = saved(new)
    progress_data["lineage_written"] = None
    write_tree(new, {".specify/sdd-rebuild/progress.json": json.dumps(progress_data, ensure_ascii=False)})
    before = tree_snapshot(new)
    result = run_rebuild(sdd_rebuild, new, "lineage")

    assert (result.code, result.out["reason"]) == (1, "lineage-changed")
    assert tree_snapshot(new) == before


@pytest.mark.parametrize("content", [b"x", None])
def test_lineage_rebuild_conflict(sdd_rebuild, tmp_path, sdd_export, content):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    write_tree(new, {".sdd-rebuild/lineage.json": content} if content else {".sdd-rebuild/other": "x"})
    before = tree_snapshot(new)
    result = run_rebuild(sdd_rebuild, new, "lineage")

    assert (result.code, result.out["reason"]) == (3, "rebuild-conflict")
    assert tree_snapshot(new) == before


def test_lineage_needs_verify_to_pass(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = confirmed(sdd_rebuild, tmp_path, sdd_export)
    result = run_rebuild(sdd_rebuild, new, "lineage")

    assert (result.code, result.out["reason"]) == (1, "mismatch-documents")
    assert not (new / ".sdd-rebuild").exists()


def test_lineage_invalid_when_the_progress_was_edited(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    data = saved(new)
    data["pending_decided"] = []
    data["source"]["nutrients"]["features"][0]["requirements"][0]["status"] = "pending"
    write_tree(new, {".specify/sdd-rebuild/progress.json": json.dumps(data, ensure_ascii=False)})
    result = run_rebuild(sdd_rebuild, new, "lineage")

    assert (result.code, result.out["reason"]) == (1, "invalid")
    assert [e["check"] for e in result.out["errors"]] == ["pending-undecided"]
    assert not (new / ".sdd-rebuild").exists()


@pytest.mark.parametrize("which", ["lineage_problems", "generation_problems"])
def test_lineage_internal_when_006_disagrees(sdd_rebuild, tmp_path, sdd_export, monkeypatch, which):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    monkeypatch.setattr(sdd_export, which, lambda *args: [sdd_export.Problem("field", "features[0].id", "no")])
    result = run_rebuild(sdd_rebuild, new, "lineage")

    assert (result.code, result.out["reason"]) == (1, "internal")
    assert result.out["errors"][0]["check"] in ("lineage-format", "next-export")
    assert not (new / ".sdd-rebuild").exists()


def test_lineage_os_error(sdd_rebuild, tmp_path, sdd_export, monkeypatch):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    (new / ".sdd-rebuild").mkdir()

    def failing_replace(source, target):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(os, "replace", failing_replace)
    result = run_rebuild(sdd_rebuild, new, "lineage")
    monkeypatch.undo()

    assert (result.code, result.out["reason"]) == (1, "os-error")
    assert list((new / ".sdd-rebuild").iterdir()) == []
    assert saved(new)["lineage_written"] is None


def test_lineage_needs_confirmed_progress(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)

    assert run_rebuild(sdd_rebuild, new, "lineage").out["reason"] == "no-progress"


# ---------------------------------------------------- (T020) focus, clear


def test_focus_points_at_the_first_generated_spec(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    assert run_rebuild(sdd_rebuild, new, "focus").out["reason"] == "no-progress"  # before the lineage
    ok(run_rebuild(sdd_rebuild, new, "lineage"))
    before = tree_snapshot(new)
    out = ok(run_rebuild(sdd_rebuild, new, "focus"))

    assert out == {"feature_directory": "specs/001-deploy", "previous": "specs/002-status", "changed": True}
    assert json.loads((new / ".specify/feature.json").read_bytes()) == {"feature_directory": "specs/001-deploy"}
    assert tree_changes(before, tree_snapshot(new))["changed"] == [".specify/feature.json"]
    again = ok(run_rebuild(sdd_rebuild, new, "focus"))
    assert again == {"feature_directory": "specs/001-deploy", "previous": "specs/001-deploy", "changed": False}


def test_focus_skips_existing_specs_and_may_have_nothing_to_point_at(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path, specs={"001-deploy": "# d\n", "002-status": "# s\n"})
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export, new=new)
    for feature, folder in zip(progress["target"]["features"], ("specs/001-deploy", "specs/002-status")):
        feature["existing_spec"] = folder
    progress["constitution"]["action"] = "keep"
    progress["generation"]["constitution"] = "not-needed"
    ok(save(sdd_rebuild, new, progress))
    confirm(sdd_rebuild, new, progress)
    ok(run_rebuild(sdd_rebuild, new, "lineage"))
    out = ok(run_rebuild(sdd_rebuild, new, "focus"))

    assert out == {"feature_directory": None, "previous": None, "changed": False}
    assert not (new / ".specify/feature.json").exists()


def test_focus_refuses_when_verify_fails_or_feature_json_is_odd(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = ready(sdd_rebuild, tmp_path, sdd_export)
    ok(run_rebuild(sdd_rebuild, new, "lineage"))
    (new / "specs" / "001-deploy" / "spec.md").unlink()
    result = run_rebuild(sdd_rebuild, new, "focus")
    assert (result.code, result.out["reason"]) == (1, "mismatch-documents")
    write_tree(new, {"specs/001-deploy/spec.md": "# Feature Specification: deploy\n"})
    (new / ".specify/feature.json").unlink()
    (new / ".specify/feature.json").mkdir()
    result = run_rebuild(sdd_rebuild, new, "focus")
    assert (result.code, result.out["reason"]) == (1, "not-regular")


def test_clear(sdd_rebuild, tmp_path, sdd_export):
    old, new, progress = started(sdd_rebuild, tmp_path, sdd_export)
    write_tree(new, {".sdd-rebuild/lineage.json": "keep me"})
    out = ok(run_rebuild(sdd_rebuild, new, "clear"))

    assert out == {"cleared": True}
    assert not (new / ".specify/sdd-rebuild").exists()
    assert (new / ".sdd-rebuild/lineage.json").read_text() == "keep me"
    assert ok(run_rebuild(sdd_rebuild, new, "clear")) == {"cleared": False}


def test_clear_unreadable_progress_and_conflict(sdd_rebuild, tmp_path, sdd_export):
    new = make_rebuild_new(tmp_path)
    write_tree(new, {".specify/sdd-rebuild/progress.json": "broken", ".specify/sdd-rebuild/.gitignore": OWN_GITIGNORE})
    assert ok(run_rebuild(sdd_rebuild, new, "clear")) == {"cleared": True}
    write_tree(new, {".specify/sdd-rebuild/progress.json": "broken", ".specify/sdd-rebuild/mine": "x"})
    before = tree_snapshot(new)
    result = run_rebuild(sdd_rebuild, new, "clear")

    assert (result.code, result.out["reason"]) == (1, "conflict")
    assert tree_snapshot(new) == before
