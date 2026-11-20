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
