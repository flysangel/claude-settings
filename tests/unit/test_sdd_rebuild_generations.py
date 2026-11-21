"""Round trips between sdd-export (006) and sdd-rebuild (007), generation after generation.

Every test runs the real 006 script and the real 007 script in temporary folders; only Spec Kit's generation of the
constitution and the specs is simulated (a folder with a spec.md and .specify/feature.json). Every rebuild asserts
that the lineage it wrote is read by 006 as present, one generation up, and that the old project was not changed.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (
    on_this_platform,
    SDD_EXPORT_FIXTURES,
    SDD_REBUILD_FIXTURES,
    export_fixture,
    export_with_006,
    git_commit_all,
    git_run,
    keep_all_progress,
    make_old_project,
    make_rebuild_new,
    make_rebuild_old,
    place_export,
    run_export,
    run_rebuild,
    simulate_constitution,
    simulate_specify,
    tree_snapshot,
    write_tree,
)

pytestmark = pytest.mark.usefixtures("export_env")

TODAY = "2026-11-21"


@pytest.fixture(autouse=True)
def fixed_time(sdd_rebuild, sdd_export, monkeypatch):
    monkeypatch.setattr(sdd_rebuild, "utc_today", lambda: TODAY)
    monkeypatch.setattr(sdd_rebuild, "utc_now", lambda: "2026-11-21T08:00:00Z")
    monkeypatch.setattr(sdd_export, "utc_today", lambda: "2026-11-20")


# ------------------------------------------------------------ (T049) helpers


def ok(result):
    assert result.code == 0, (result.out, result.err)
    return result.out


def save(module, new, progress, *flags):
    return ok(run_rebuild(module, new, "save", *flags, stdin=progress))


def old_lineage_choice(check: dict) -> str:
    if check["old_lineage"] == "present":
        return "used"
    if check["old_lineage"] == "none" and not check["needs_old_lineage"]:
        return "not-needed"
    return "skipped"


def rebuild(R, E, old: Path, parent: Path, name: str, decide=None, choice: str | None = None,
            specs: dict[str, str] | None = None, pattern_named: str | None = None):
    """A whole rebuild with 007's commands, from check to clear; returns (new project, lineage).

    specs: spec folders the new project already holds. pattern_named: the id of a feature whose spec Spec Kit puts in
    a folder named like a secret pattern; claim refuses it and the folder is renamed, as SKILL.md says.
    """
    new = make_rebuild_new(parent, name, specs=specs)
    before = tree_snapshot(old)
    check = ok(run_rebuild(R, new, "check", "--old", str(old)))
    nutrients = check["nutrients"]
    progress = keep_all_progress(check["old"]["path"], nutrients, choice or old_lineage_choice(check))
    if decide:
        decide(progress, nutrients)
    save(R, new, progress)
    preview = run_rebuild(R, new, "preview")
    assert preview.code == 0, preview.out["errors"]
    progress.update(phase="confirmed", stage="summary")
    save(R, new, progress)
    simulate_constitution(new)
    progress["generation"]["constitution"] = "reviewed"
    save(R, new, progress)
    for feature in progress["target"]["features"]:
        if feature["id"] == pattern_named:
            folder = simulate_specify(new, f"sk-learn-{feature['id']}-pipeline")
            assert run_rebuild(R, new, "claim", feature["id"]).out["reason"] == "secret"
            renamed = folder.replace("sk-learn", "sklearn")
            (new / folder).rename(new / renamed)
            feature["spec_dir"] = ok(run_rebuild(R, new, "claim", feature["id"], "--dir", renamed))["spec_dir"]
        else:
            simulate_specify(new, feature["id"])
            feature["spec_dir"] = ok(run_rebuild(R, new, "claim", feature["id"]))["spec_dir"]
        feature["reviewed"] = True
        save(R, new, progress)
    ok(run_rebuild(R, new, "verify"))
    ok(run_rebuild(R, new, "lineage"))
    ok(run_rebuild(R, new, "focus"))
    assert ok(run_rebuild(R, new, "clear")) == {"cleared": True}
    assert tree_snapshot(old) == before, "the old project was changed"
    raw = (new / ".sdd-rebuild" / "lineage.json").read_bytes()
    lineage = json.loads(raw)
    assert raw == E.serialize(lineage, "lineage")
    seen = ok(run_export(E, new, "check"))
    assert (seen["lineage"], seen["generation"]) == ("present", nutrients["generation"] + 1)
    assert E.lineage_problems(lineage) == []
    assert E.generation_problems(lineage, lineage, None) == []
    return new, lineage


def draft_from_lineage(lineage: dict, project: str) -> dict:
    """What the next /sdd-export of a rebuilt project drafts when everything is kept as it is."""
    def principle(item):
        source = item["source"] if item["source"] != "rebuild" else "constitution"
        return {**{k: item[k] for k in ("id", "origin", "title", "text", "revised", "derived_from")}, "source": source,
                "status": "confirmed", "evidence": [".specify/memory/constitution.md"]}

    def requirement(item, spec):
        return {**{k: item[k] for k in ("id", "origin", "kind", "text", "revised", "derived_from")}, "source": "spec",
                "status": "confirmed", "evidence": [spec]}

    def feature(item):
        spec = f"{item['spec_dir']}/spec.md"
        return {**{k: item[k] for k in ("id", "origin", "title", "summary", "revised", "derived_from")}, "source": "spec",
                "spec": spec, "depends_on": list(item["depends_on"]),
                "requirements": [requirement(r, spec) for r in item["requirements"]]}

    def lesson(item):
        return {**{k: item[k] for k in ("id", "origin", "kind", "title", "text", "revised", "derived_from")},
                "status": "confirmed", "evidence": [".sdd-rebuild/lineage.json"]}

    return {
        "generation": lineage["generation"], "project": project, "language": "zh-Hant",
        "scope": {"coverage": "full", "included": []},
        "principles": [principle(p) for p in lineage["principles"]],
        "features": [feature(f) for f in lineage["features"]],
        "lessons": [lesson(l) for l in lineage["lessons"]],
        "discarded": copy.deepcopy(lineage["discarded"]),
    }


def validate(E, project: Path, draft: dict):
    return run_export(E, project, "validate", stdin=json.dumps(draft, ensure_ascii=False))


def checks_of(result) -> list[str]:
    return [error["check"] for error in result.out.get("errors", [])]


def new_requirement(rid: str, generation: int, spec: str) -> dict:
    return {"id": rid, "origin": generation, "kind": "functional", "text": f"新的需求 {rid}。", "revised": [],
            "derived_from": [], "source": "spec", "status": "confirmed", "evidence": [spec]}


def items(lineage: dict) -> dict:
    found = {}
    for section in ("principles", "features", "lessons"):
        for item in lineage[section]:
            found[item["id"]] = item
            for requirement in item.get("requirements", []):
                found[requirement["id"]] = requirement
    return found


def entry(section, **fields):
    base = {"from": []}
    if section == "features":
        base.update(depends_on=[], existing_spec=None, spec_dir=None, reviewed=False)
    return {**base, **fields}


def feature_index(progress, fid):
    return next(i for i, f in enumerate(progress["target"]["features"]) if f["id"] == fid)


# --------------------------------------------- generation 1 and generation 2


def gen1_with_pending() -> dict:
    draft = export_fixture("gen1-draft.json")
    status_list = draft["features"][1]["requirements"][0]
    status_list.update(status="pending", evidence=[])
    return draft


def decide_gen2(progress, nutrients):
    target = progress["target"]
    deploy = target["features"][0]
    deploy["summary"] = "維護者以一行指令部署，並先檢查衝突。"  # modified
    deploy["requirements"] = [r for r in deploy["requirements"] if r["id"] != "deploy-symlink"]
    target["lessons"] = [l for l in target["lessons"] if l["id"] != "json-format"]
    progress["discards"] = [{"id": "deploy-symlink", "text": None, "reason": "Windows 需要管理員權限。"},
                            {"id": "json-format", "text": None, "reason": None}]
    target["principles"].append(entry("principles", id="spec-driven", basis="new", title="規格先行", text="每個功能 MUST 先有 spec。"))
    target["features"].append(entry("features", id="report", basis="new", title="差異報告", summary="列出與來源不同的檔案。",
                                    depends_on=["deploy"], requirements=[
                                        entry("requirements", id="report-diff", basis="new", kind="functional",
                                              text="列出與來源內容不同的已部署檔案。")]))
    progress["pending_decided"] = ["status-list"]  # kept as a fact


def generation_two(R, E, tmp_path):
    old = make_rebuild_old(E, tmp_path, gen1_with_pending(), name="gen1")
    return rebuild(R, E, old, tmp_path, "gen2", decide_gen2)


def test_a_lineage_written_by_007_passes_006(sdd_rebuild, sdd_export, tmp_path):
    # SC-006: without any manual step, the rebuilt project adds one spec and exports the next nutrients.
    old = make_rebuild_old(sdd_export, tmp_path, export_fixture("gen1-draft.json"), name="gen1")
    new, lineage = rebuild(sdd_rebuild, sdd_export, old, tmp_path, "gen2")
    folder = simulate_specify(new, "extra")
    draft = draft_from_lineage(lineage, "my-tool")
    draft["features"].append({"id": "extra", "origin": 2, "title": "額外", "summary": "新增的功能。", "revised": [],
                              "derived_from": [], "source": "spec", "spec": f"{folder}/spec.md", "depends_on": [],
                              "requirements": [new_requirement("extra-one", 2, f"{folder}/spec.md")]})
    written = export_with_006(sdd_export, new, draft)
    nutrients = json.loads((new / ".sdd-export" / "nutrients.json").read_bytes())

    assert written.out["generation"] == 2
    assert {item["id"]: item["origin"] for item in items(nutrients).values()}["extra"] == 2
    assert items(nutrients)["deploy"]["origin"] == 1


def test_generation_1_to_2(sdd_rebuild, sdd_export, tmp_path):
    new, lineage = generation_two(sdd_rebuild, sdd_export, tmp_path)
    found = items(lineage)

    assert lineage["generation"] == 2 and lineage["source"]["generation"] == 1
    assert (found["cross-platform"]["origin"], found["cross-platform"]["revised"]) == (1, [])
    assert (found["deploy"]["origin"], found["deploy"]["revised"]) == (1, [2])
    assert (found["spec-driven"]["origin"], found["spec-driven"]["source"]) == (2, "rebuild")
    assert (found["report-diff"]["origin"], found["report-diff"]["source"]) == (2, "rebuild")
    assert list(found["status-list"]) == ["id", "origin", "kind", "text", "revised", "derived_from", "source"]
    assert (found["status-list"]["origin"], found["status-list"]["revised"]) == (1, [])  # the pending item, kept
    gone = {d["id"]: d for d in lineage["discarded"]}
    assert (gone["deploy-symlink"]["discarded_in"], gone["json-format"]["discarded_in"]) == (2, 2)
    assert validate(sdd_export, new, draft_from_lineage(lineage, "my-tool")).code == 0


# ------------------------------------------------------- generation 2 to 3


def decide_gen3(progress, nutrients):
    target = progress["target"]
    features = target["features"]
    status, report = features[feature_index(progress, "status")], features[feature_index(progress, "report")]
    merged = entry("features", id="overview", basis="derived", from_=None, title="總覽", summary="狀態與差異。",
                   depends_on=["deploy"], requirements=[
                       entry("requirements", id="overview-list", basis="derived", kind="functional",
                             text="列出狀態與差異。", **{"from": ["status-list", "report-diff"]})])
    merged.pop("from_")
    merged["from"] = ["status", "report"]
    target["features"] = [f for f in features if f["id"] not in ("status", "report")] + [merged]
    target["features"].append(entry("features", id="deploy-check", basis="derived", title="部署前檢查",
                                    summary="部署前檢查衝突。", depends_on=["deploy"], **{"from": ["deploy"]},
                                    requirements=[entry("requirements", id="deploy-check-run", basis="new",
                                                        kind="functional", text="部署前執行檢查。")]))


def generation_three(R, E, tmp_path):
    gen2, lineage2 = generation_two(R, E, tmp_path)
    export_with_006(E, gen2, draft_from_lineage(lineage2, "my-tool"))
    return rebuild(R, E, gen2, tmp_path, "gen3", decide_gen3)


def test_generation_2_to_3_merge_and_split_keeping_the_original(sdd_rebuild, sdd_export, tmp_path):
    new, lineage = generation_three(sdd_rebuild, sdd_export, tmp_path)
    found = items(lineage)

    assert (found["overview"]["origin"], found["overview"]["derived_from"]) == (3, ["status", "report"])
    assert (found["overview-list"]["origin"], found["overview-list"]["derived_from"]) == (3, ["status-list", "report-diff"])
    assert not {"status", "report", "status-list", "report-diff"} & {d["id"] for d in lineage["discarded"]}
    assert (found["deploy"]["origin"], found["deploy"]["derived_from"]) == (1, [])  # the original stays
    assert found["deploy-check"]["derived_from"] == ["deploy"]
    assert (found["deploy-check"]["source"], found["deploy-check"]["spec"]) == ("spec", "specs/001-deploy/spec.md")
    assert validate(sdd_export, new, draft_from_lineage(lineage, "my-tool")).code == 0


# ---------------------------------------- generation 3 to 4: merge, then split


def gen3_old(E, tmp_path: Path) -> Path:
    """The generation-3 old project of 006's fixtures: lineage-gen3.json and gen3-draft.json exported by 006."""
    files = {"specs/001-deploy/spec.md": "# d\n", "specs/002-overview/spec.md": "# o\n",
             ".specify/memory/constitution.md": "# Constitution\n",
             ".sdd-rebuild/lineage.json": (SDD_EXPORT_FIXTURES / "lineage-gen3.json").read_bytes()}
    root = make_old_project(tmp_path, "gen3", files=files)
    export_with_006(E, root, export_fixture("gen3-draft.json"))
    return root


def decide_gen4(progress, nutrients):
    features = progress["target"]["features"]
    overview = features.pop(feature_index(progress, "overview"))
    features.append(entry("features", id="overview-files", basis="derived", title="檔案總覽", summary="列出檔案。",
                          depends_on=["deploy"], **{"from": ["overview"]}, requirements=[
                              entry("requirements", id="files-list", basis="derived", kind="functional",
                                    text="列出已部署的檔案。", **{"from": ["overview-list"]})]))
    features.append(entry("features", id="overview-diff", basis="derived", title="差異總覽", summary="標出差異。",
                          depends_on=["deploy"], **{"from": ["overview"]}, requirements=[
                              entry("requirements", id="diff-mark", basis="derived", kind="functional",
                                    text="標出與來源不同的檔案。", **{"from": ["overview-list"]})]))


def generation_four(R, E, tmp_path):
    return rebuild(R, E, gen3_old(E, tmp_path), tmp_path, "gen4", decide_gen4)


def test_generation_3_to_4_merge_then_split_keeps_the_earliest_sources(sdd_rebuild, sdd_export, tmp_path):
    new, lineage = generation_four(sdd_rebuild, sdd_export, tmp_path)
    found = items(lineage)

    assert found["files-list"]["derived_from"] == ["overview-list", "status-list", "report-diff"]
    assert found["diff-mark"]["derived_from"] == ["overview-list", "status-list", "report-diff"]
    assert found["overview-files"]["derived_from"] == ["overview", "status", "report"]
    draft = draft_from_lineage(lineage, "my-tool")
    assert validate(sdd_export, new, draft).code == 0
    for taken in ("status-list", "overview-list", "report-diff"):
        reuse = copy.deepcopy(draft)
        reuse["features"][0]["requirements"].append(new_requirement(taken, 4, draft["features"][0]["spec"]))
        assert "id-reused" in checks_of(validate(sdd_export, new, reuse)), taken


def test_without_the_ancestors_a_merged_away_id_could_be_reused(sdd_rebuild, sdd_export, tmp_path):
    # The control: the same lineage with only the direct sources (composed by hand, not by 007).
    new, lineage = generation_four(sdd_rebuild, sdd_export, tmp_path)
    direct = copy.deepcopy(lineage)
    for item in items(direct).values():
        if item["id"] in ("files-list", "diff-mark"):
            item["derived_from"] = ["overview-list"]
        if item["id"] in ("overview-files", "overview-diff"):
            item["derived_from"] = ["overview"]
    (new / ".sdd-rebuild" / "lineage.json").write_bytes(sdd_export.serialize(direct, "lineage"))
    draft = draft_from_lineage(direct, "my-tool")
    draft["features"][0]["requirements"].append(new_requirement("status-list", 4, draft["features"][0]["spec"]))

    assert validate(sdd_export, new, draft).code == 0  # status-list slips through: the expansion is needed


# --------------------------------------- generation 4 to 5: merge at export


def export_gen4_with_a_merge(E, gen4: Path, lineage4: dict) -> dict:
    draft = draft_from_lineage(lineage4, "my-tool")
    files_feature = next(f for f in draft["features"] if f["id"] == "overview-files")
    diff_feature = next(f for f in draft["features"] if f["id"] == "overview-diff")
    files_list, diff_mark = files_feature["requirements"][0], diff_feature["requirements"][0]
    merged = {**files_list, "id": "files-all", "origin": 4, "text": "列出檔案並標出差異。", "revised": [],
              "derived_from": ["files-list", "diff-mark"]}
    files_feature["requirements"] = [merged]
    diff_feature["requirements"] = [new_requirement("diff-note", 4, diff_feature["spec"])]
    export_with_006(E, gen4, draft)
    return draft


def generation_five(R, E, tmp_path, choice=None):
    gen4, lineage4 = generation_four(R, E, tmp_path)
    draft4 = export_gen4_with_a_merge(E, gen4, lineage4)
    new, lineage5 = rebuild(R, E, gen4, tmp_path, "gen5", choice=choice)
    return gen4, draft4, new, lineage5


def test_export_time_merge_cannot_record_the_ancestors(sdd_rebuild, sdd_export, tmp_path):
    gen4, lineage4 = generation_four(sdd_rebuild, sdd_export, tmp_path)
    draft = draft_from_lineage(lineage4, "my-tool")
    files_feature = next(f for f in draft["features"] if f["id"] == "overview-files")
    diff_feature = next(f for f in draft["features"] if f["id"] == "overview-diff")
    files_feature["requirements"] = [{**files_feature["requirements"][0], "id": "files-all", "origin": 4,
                                      "derived_from": ["files-list", "diff-mark", "overview-list", "status-list",
                                                       "report-diff"]}]
    diff_feature["requirements"] = [new_requirement("diff-note", 4, diff_feature["spec"])]

    assert checks_of(validate(sdd_export, gen4, draft)).count("derived-unknown") == 3


def test_generation_4_to_5_takes_the_ancestors_from_the_old_lineage(sdd_rebuild, sdd_export, tmp_path):
    gen4, draft4, new, lineage5 = generation_five(sdd_rebuild, sdd_export, tmp_path)
    found = items(lineage5)

    assert found["files-all"]["derived_from"] == ["files-list", "diff-mark", "overview-list", "status-list", "report-diff"]
    draft = draft_from_lineage(lineage5, "my-tool")
    assert validate(sdd_export, new, draft).code == 0
    draft["features"][0]["requirements"].append(new_requirement("status-list", 5, draft["features"][0]["spec"]))
    assert "id-reused" in checks_of(validate(sdd_export, new, draft))


def test_kept_items_with_a_longer_derived_from_are_not_a_change(sdd_rebuild, sdd_export, tmp_path):
    gen4, draft4, gen5, lineage5 = generation_five(sdd_rebuild, sdd_export, tmp_path)
    before = next(r for f in draft4["features"] for r in f["requirements"] if r["id"] == "files-all")
    after = items(lineage5)["files-all"]

    assert len(after["derived_from"]) > len(before["derived_from"])
    assert after["revised"] == before["revised"] == []
    result = validate(sdd_export, gen5, draft_from_lineage(lineage5, "my-tool"))
    assert result.code == 0 and "revision-unmarked" not in checks_of(result)
    export_with_006(sdd_export, gen5, draft_from_lineage(lineage5, "my-tool"))
    gen6, lineage6 = rebuild(sdd_rebuild, sdd_export, gen5, tmp_path, "gen6")
    assert json.dumps(items(lineage6)["files-all"]["derived_from"]) == json.dumps(after["derived_from"])


# -------------------------------------------------------- SC-006, the trace


def test_sc006_every_item_traces_back_to_generation_1(sdd_rebuild, sdd_export, tmp_path):
    gen4, draft4, gen5, lineage5 = generation_five(sdd_rebuild, sdd_export, tmp_path)
    first = {item["id"] for item in items(export_fixture("gen1-draft.json")).values()}
    created = {}  # ids created as new items, with the generation that created them
    for name in ("gen2-draft.json", "gen3-draft.json"):
        for item in items(export_fixture(name)).values():
            if not item["derived_from"]:
                created.setdefault(item["id"], item["origin"])
    for item in items(draft4).values():
        if not item["derived_from"]:
            created.setdefault(item["id"], item["origin"])

    for item in items(lineage5).values():
        if item["origin"] == 1:
            assert item["id"] in first, item["id"]
        elif item["derived_from"]:
            assert set(item["derived_from"]) & first, item["id"]
        else:
            assert created.get(item["id"]) == item["origin"], item["id"]
    gone = {d["id"] for d in lineage5["discarded"]}
    assert {"deploy-symlink", "json-format", "audit", "audit-log"} <= gone
    draft = draft_from_lineage(lineage5, "my-tool")
    draft["lessons"].append({"id": "json-format", "origin": 1, "kind": "decision", "title": "x", "text": "y",
                             "revised": [], "derived_from": [], "status": "confirmed",
                             "evidence": [".sdd-rebuild/lineage.json"]})
    assert {"discarded-active"} <= set(checks_of(validate(sdd_export, gen5, draft)))
    assert items(lineage5)["diff-note"]["origin"] == 4  # added at an export: its own generation


def test_a_requirement_added_in_a_rebuild_has_that_generation(sdd_rebuild, sdd_export, tmp_path):
    new, lineage = generation_two(sdd_rebuild, sdd_export, tmp_path)

    assert items(lineage)["report-diff"]["origin"] == 2


# ------------------------------------------- the two accepted limitations


def test_known_limitation_1_sources_recorded_by_an_earlier_export_of_the_same_generation_are_lost(
        sdd_rebuild, sdd_export, tmp_path):
    """Known limitation accepted by the maintainer (research R5, 2026-11-20).

    Within one generation, an export splits an item that an earlier export of that generation created, and a later
    export merges the parts again. The later export replaces the nutrients, the lineage never knew the first item,
    so the rebuild cannot recover it.
    """
    gen2, lineage2 = generation_two(sdd_rebuild, sdd_export, tmp_path)
    draft = draft_from_lineage(lineage2, "my-tool")
    spec = draft["features"][0]["spec"]
    draft["features"][0]["requirements"].append(new_requirement("draft-a", 2, spec))
    export_with_006(sdd_export, gen2, draft)  # export 1 creates draft-a
    part = {**new_requirement("part-one", 2, spec), "derived_from": ["draft-a"]}
    draft["features"][0]["requirements"][-1:] = [part, {**part, "id": "part-two"}]
    export_with_006(sdd_export, gen2, draft)  # export 2 splits it and records draft-a as the source
    draft["features"][0]["requirements"][-2:] = [{**new_requirement("whole", 2, spec), "derived_from": ["part-one", "part-two"]}]
    export_with_006(sdd_export, gen2, draft)  # export 3 merges the parts again
    new, lineage3 = rebuild(sdd_rebuild, sdd_export, gen2, tmp_path, "gen3")

    assert items(lineage3)["whole"]["derived_from"] == ["part-one", "part-two"]
    assert "draft-a" not in json.dumps(lineage3)


def test_known_limitation_2_the_sources_of_a_discarded_item_are_lost(sdd_rebuild, sdd_export, tmp_path):
    """Known limitation accepted by the maintainer (research R5, 2026-11-20).

    A discard record has no derived_from: the sources of a discarded item stop at that discard. The discarded item
    itself stays in discarded and cannot be reused; ids only it kept in sight can.
    """
    def discard_overview(progress, nutrients):
        index = feature_index(progress, "overview")
        progress["target"]["features"].pop(index)
        progress["discards"] = [{"id": "overview", "text": None, "reason": None},
                                {"id": "overview-list", "text": None, "reason": None}]

    gen4, lineage4 = rebuild(sdd_rebuild, sdd_export, gen3_old(sdd_export, tmp_path), tmp_path, "gen4", discard_overview)
    text = json.dumps({k: lineage4[k] for k in ("principles", "features", "lessons")})

    assert "status-list" not in text
    assert {"overview", "overview-list"} <= {d["id"] for d in lineage4["discarded"]}
    draft = draft_from_lineage(lineage4, "my-tool")
    spec = draft["features"][0]["spec"]
    reuse_history = copy.deepcopy(draft)
    reuse_history["features"][0]["requirements"].append(new_requirement("status-list", 4, spec))
    assert validate(sdd_export, gen4, reuse_history).code == 0
    reuse_discarded = copy.deepcopy(draft)
    reuse_discarded["features"][0]["requirements"].append(new_requirement("overview-list", 4, spec))
    assert "id-reused" in checks_of(validate(sdd_export, gen4, reuse_discarded))


# ------------------------------------ (T058) the old lineage cannot be used


def gen4_exported(R, E, tmp_path) -> Path:
    gen4, lineage4 = generation_four(R, E, tmp_path)
    export_gen4_with_a_merge(E, gen4, lineage4)
    return gen4


@pytest.mark.parametrize("case, state", [
    ("removed", "none"), ("other-generation", "mismatch"), ("garbage", "unreadable"), ("broken", "invalid"),
    ("newer", "newer"), ("foreign", "conflict"),
])
def test_an_unusable_old_lineage_can_be_skipped(sdd_rebuild, sdd_export, tmp_path, case, state):
    old = gen4_exported(sdd_rebuild, sdd_export, tmp_path)
    path = old / ".sdd-rebuild" / "lineage.json"
    if case == "removed":
        path.unlink()
    else:
        path.write_bytes({
            "other-generation": (SDD_EXPORT_FIXTURES / "lineage-gen3.json").read_bytes(),
            "garbage": b"{not json",
            "broken": b'{"tool": "sdd-rebuild", "schema": 1}',
            "newer": b'{"tool": "sdd-rebuild", "schema": 2}',
            "foreign": b'{"tool": "something-else"}',
        }[case])
    probe = make_rebuild_new(tmp_path, "probe")
    check = ok(run_rebuild(sdd_rebuild, probe, "check", "--old", str(old)))
    assert (check["old_lineage"], check["needs_old_lineage"]) == (state, True)
    assert bool(check["old_lineage_errors"]) == (state in ("unreadable", "invalid"))
    for refused in ("used", "not-needed"):
        progress = keep_all_progress(check["old"]["path"], check["nutrients"], refused)
        result = run_rebuild(sdd_rebuild, probe, "save", stdin=progress)
        assert (result.out["reason"], result.out["path"]) == ("invalid", "old_lineage"), refused

    new, lineage5 = rebuild(sdd_rebuild, sdd_export, old, tmp_path, "gen5", choice="skipped")

    # Only the nutrients gave the ancestors: what only the old lineage recorded is lost (README: known limitation).
    assert items(lineage5)["files-all"]["derived_from"] == ["files-list", "diff-mark"]
    draft = draft_from_lineage(lineage5, "my-tool")
    draft["features"][0]["requirements"].append(new_requirement("status-list", 5, draft["features"][0]["spec"]))
    assert validate(sdd_export, new, draft).code == 0


def test_the_skipped_choice_is_kept_in_the_progress(sdd_rebuild, sdd_export, tmp_path):
    old = gen4_exported(sdd_rebuild, sdd_export, tmp_path)
    (old / ".sdd-rebuild" / "lineage.json").unlink()
    new = make_rebuild_new(tmp_path, "gen5")
    check = ok(run_rebuild(sdd_rebuild, new, "check", "--old", str(old)))
    save(sdd_rebuild, new, keep_all_progress(check["old"]["path"], check["nutrients"], "skipped"))

    assert ok(run_rebuild(sdd_rebuild, new, "check"))["saved"]["old_lineage"] == "skipped"


def test_a_first_generation_needs_no_old_lineage(sdd_rebuild, sdd_export, tmp_path):
    old = make_rebuild_old(sdd_export, tmp_path, export_fixture("gen1-draft.json"), name="gen1")
    new = make_rebuild_new(tmp_path, "gen2")
    check = ok(run_rebuild(sdd_rebuild, new, "check", "--old", str(old)))

    assert (check["old_lineage"], check["needs_old_lineage"]) == ("none", False)
    result = run_rebuild(sdd_rebuild, new, "save", stdin=keep_all_progress(check["old"]["path"], check["nutrients"], "skipped"))
    assert result.out["reason"] == "invalid"
    save(sdd_rebuild, new, keep_all_progress(check["old"]["path"], check["nutrients"], "not-needed"))


# ---------------------------------- content added after the confirmation (Q4)


def test_content_added_after_the_confirmation_is_new_in_this_generation(sdd_rebuild, sdd_export, tmp_path):
    old = make_rebuild_old(sdd_export, tmp_path, export_fixture("gen1-draft.json"), name="gen1")
    new = make_rebuild_new(tmp_path, "gen2")
    check = ok(run_rebuild(sdd_rebuild, new, "check", "--old", str(old)))
    progress = keep_all_progress(check["old"]["path"], check["nutrients"], "not-needed")
    save(sdd_rebuild, new, progress)
    progress.update(phase="confirmed", stage="summary")
    save(sdd_rebuild, new, progress)
    simulate_constitution(new, "# Constitution\n\n### 原則\n\n- 規則。\n\n### 維護者同意保留的規則\n\n- 每次發布 MUST 有變更紀錄。\n")
    progress["generation"]["constitution"] = "written"
    save(sdd_rebuild, new, progress)
    progress["constitution"]["governance"].append("每次發布 MUST 有變更紀錄。")  # kept in stage 9
    progress["generation"]["constitution"] = "reviewed"
    save(sdd_rebuild, new, progress)
    for feature in progress["target"]["features"]:
        simulate_specify(new, feature["id"])
        feature["spec_dir"] = ok(run_rebuild(sdd_rebuild, new, "claim", feature["id"]))["spec_dir"]
        feature["reviewed"] = True
        if feature["id"] == "deploy":  # a clarification answered in stage 10 went into the spec
            progress["deferred"].append({"item": "部署記錄的保存期限", "reason": "澄清時決定之後再定", "feature": "deploy"})
        save(sdd_rebuild, new, progress)
    assert ok(run_rebuild(sdd_rebuild, new, "verify"))["ok"] is True
    ok(run_rebuild(sdd_rebuild, new, "lineage"))
    data = ok(run_rebuild(sdd_rebuild, new, "check"))["saved"]
    assert data["baseline"]["confirmed_counts"] == {"governance": 0, "deferred": 0, "for_plan": 0}
    assert len(data["constitution"]["governance"]) == 1 and len(data["deferred"]) == 1
    lineage = json.loads((new / ".sdd-rebuild" / "lineage.json").read_bytes())
    assert "變更紀錄" not in json.dumps(lineage, ensure_ascii=False)

    draft = draft_from_lineage(lineage, "my-tool")
    draft["principles"].append({"id": "changelog", "origin": 2, "title": "變更紀錄", "text": "每次發布 MUST 有變更紀錄。",
                                "revised": [], "derived_from": [], "source": "constitution", "status": "confirmed",
                                "evidence": [".specify/memory/constitution.md"]})
    deploy = draft["features"][0]
    deploy["requirements"].append(new_requirement("deploy-log-retention", 2, deploy["spec"]))
    export_with_006(sdd_export, new, draft)
    nutrients = json.loads((new / ".sdd-export" / "nutrients.json").read_bytes())
    assert items(nutrients)["changelog"]["origin"] == 2
    assert items(nutrients)["deploy-log-retention"]["origin"] == 2


# --------------------------------------------- (T059) bytes on every platform

GOLDEN = SDD_REBUILD_FIXTURES / "lineage-from-nutrients.json"


def rebuild_fixture(R, E, tmp_path: Path, crlf: bool = False, with_lineage: bool = False, name: str = "x") -> bytes:
    old = tmp_path / f"old-{name}"
    old.mkdir()
    raw = (SDD_EXPORT_FIXTURES / "nutrients.json").read_bytes()
    lineage = (SDD_EXPORT_FIXTURES / "lineage-gen2.json").read_bytes()
    if crlf:
        raw, lineage = raw.replace(b"\n", b"\r\n"), lineage.replace(b"\n", b"\r\n")
    place_export(E, old, raw)
    if crlf:
        readme = old / ".sdd-export" / "README.md"
        readme.write_bytes(readme.read_bytes().replace(b"\n", b"\r\n"))
    if with_lineage:
        write_tree(old, {".sdd-rebuild/lineage.json": lineage})

    def decide(progress, nutrients):
        progress["pending_decided"] = ["status-report-diff"]

    new, _ = rebuild(R, E, old, tmp_path, f"new-{name}", decide)
    return (new / ".sdd-rebuild" / "lineage.json").read_bytes()


def test_the_lineage_bytes_are_fixed(sdd_rebuild, sdd_export, tmp_path):
    # The golden file was written once from this rebuild and checked field by field against data-model.md
    # "世代紀錄的組成" (generation + 1, inherited origin, revised, source and spec, spec_dir from claim, no
    # status or evidence, the nutrients' discarded records unchanged).
    data = rebuild_fixture(sdd_rebuild, sdd_export, tmp_path)

    assert data == GOLDEN.read_bytes()
    assert b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("with_lineage", [False, True])
def test_crlf_input_gives_the_same_bytes(sdd_rebuild, sdd_export, tmp_path, with_lineage):
    lf = rebuild_fixture(sdd_rebuild, sdd_export, tmp_path, with_lineage=with_lineage, name="lf")
    crlf = rebuild_fixture(sdd_rebuild, sdd_export, tmp_path, crlf=True, with_lineage=with_lineage, name="crlf")

    assert lf == crlf


def test_the_gitattributes_keep_the_lineage_lf_in_an_autocrlf_clone(sdd_rebuild, sdd_export, tmp_path):
    rebuild_fixture(sdd_rebuild, sdd_export, tmp_path)
    new = tmp_path / "new-x"
    assert (new / ".sdd-rebuild" / ".gitattributes").read_bytes() == (
        b"# Created by sdd-rebuild; keeps the lineage LF on every platform.\n* text eol=lf\n")
    git_commit_all(new, "rebuilt")
    clone = tmp_path / "clone"
    subprocess.run(["git", "-c", "core.autocrlf=true", "clone", "--quiet", str(new), str(clone)], check=True,
                   capture_output=True)
    git_run(clone, "config", "core.autocrlf", "true")
    (clone / ".sdd-rebuild" / "lineage.json").unlink()
    git_run(clone, "checkout", "--", ".sdd-rebuild/lineage.json")

    assert b"\r\n" not in (clone / ".sdd-rebuild" / "lineage.json").read_bytes()


def test_outputs_are_the_same_bytes_for_lf_and_crlf_input(sdd_rebuild, sdd_export, tmp_path):
    outputs = []
    for crlf in (False, True):
        old = tmp_path / f"old-{crlf}"
        old.mkdir()
        raw = (SDD_EXPORT_FIXTURES / "nutrients.json").read_bytes()
        place_export(sdd_export, old, raw.replace(b"\n", b"\r\n") if crlf else raw)
        new = make_rebuild_new(tmp_path, f"new-{crlf}")
        check = ok(run_rebuild(sdd_rebuild, new, "check", "--old", str(old)))
        progress = keep_all_progress(check["old"]["path"], check["nutrients"], "skipped")
        progress["pending_decided"] = ["status-report-diff"]
        save(sdd_rebuild, new, progress)
        outputs.append(run_rebuild(sdd_rebuild, new, "preview").raw)

    assert outputs[0] == outputs[1]


# ------------------------------------- (T076) a secret put into the old project by hand

# A made-up value that only has to look like a token to 006's patterns; never a real credential.
FAKE_TOKEN = "ghp_" + "Zq7Fake9Token" * 2


def recording(monkeypatch):
    """Record every 007 result while the round trip runs (the helpers above call run_rebuild by name)."""
    import sys

    results = []
    real = run_rebuild

    def run(*args, **kwargs):
        result = real(*args, **kwargs)
        results.append((args[2:], result))
        return result

    monkeypatch.setattr(sys.modules[__name__], "run_rebuild", run)
    return results


def leaked(results) -> list:
    return [argv for argv, r in results if FAKE_TOKEN in r.raw.decode("utf-8") or FAKE_TOKEN in r.err]


def test_hand_edited_nutrients_with_a_secret_stop_at_check(sdd_rebuild, sdd_export, tmp_path, monkeypatch):
    old = make_rebuild_old(sdd_export, tmp_path, export_fixture("gen1-draft.json"), name="gen1")
    path = old / ".sdd-export" / "nutrients.json"
    data = json.loads(path.read_bytes())
    data["lessons"][0]["text"] = f"password={FAKE_TOKEN}"
    path.write_bytes(sdd_export.serialize(data, "nutrients"))
    own = run_export(sdd_export, old, "check")  # 006 refuses them itself, with the same paths that 007 shows
    results = recording(monkeypatch)
    new = make_rebuild_new(tmp_path, "gen2")
    check = run_rebuild(sdd_rebuild, new, "check", "--old", str(old))
    first = run_rebuild(sdd_rebuild, new, "save", stdin=keep_all_progress(os.path.realpath(old), data, "not-needed"))

    assert (check.code, check.out["reason"], check.out["nutrients"]) == (3, "nutrients-invalid", None)
    assert [(e["check"], e["path"]) for e in check.out["nutrients_errors"]] == [("secret", "lessons[0].text")]
    assert (own.code, own.out["reason"], own.out["existing"]) == (3, "nutrients-invalid", None)
    assert own.out["errors"] == check.out["nutrients_errors"]
    assert FAKE_TOKEN not in own.raw.decode("utf-8") + own.err
    assert (first.code, first.out["reason"]) == (1, "source")
    assert not (new / ".specify" / "sdd-rebuild").exists() and not (new / ".sdd-rebuild").exists()
    assert leaked(results) == []


def test_an_old_lineage_with_a_secret_never_reaches_the_new_lineage(sdd_rebuild, sdd_export, tmp_path, monkeypatch):
    gen2, lineage2 = generation_two(sdd_rebuild, sdd_export, tmp_path)
    export_with_006(sdd_export, gen2, draft_from_lineage(lineage2, "my-tool"))
    path = gen2 / ".sdd-rebuild" / "lineage.json"
    data = json.loads(path.read_bytes())
    data["lessons"][0]["text"] += f" token: {FAKE_TOKEN}"
    path.write_bytes(sdd_export.serialize(data, "lineage"))
    results = recording(monkeypatch)

    new, lineage3 = rebuild(sdd_rebuild, sdd_export, gen2, tmp_path, "gen3")

    assert results[0][1].out["old_lineage"] == "invalid"
    assert FAKE_TOKEN not in (new / ".sdd-rebuild" / "lineage.json").read_text(encoding="utf-8")
    assert len(results) > 10 and leaked(results) == []


# ------------- generations whose new projects hold spec folders named like secret patterns


def test_generations_1_to_3_with_spec_folders_named_like_secret_patterns(sdd_rebuild, sdd_export, tmp_path):
    """A folder of the maintainer's named like a pattern sits in each new project, and in generation 3 Spec Kit names a
    generated spec like one (claim refuses it; the folder is renamed). Every step reads back what the last wrote."""
    old = make_rebuild_old(sdd_export, tmp_path, gen1_with_pending(), name="gen1")
    gen2, lineage2 = rebuild(sdd_rebuild, sdd_export, old, tmp_path, "gen2", decide_gen2,
                             specs={"000-sk-learn-pipeline-integration": "# 既有的 spec\n"})
    assert (gen2 / "specs/000-sk-learn-pipeline-integration/spec.md").is_file()
    export_with_006(sdd_export, gen2, draft_from_lineage(lineage2, "my-tool"))
    gen3, lineage3 = rebuild(sdd_rebuild, sdd_export, gen2, tmp_path, "gen3", decide_gen3,
                             specs={name: "# 既有的 spec\n" for name in on_this_platform(["000-token=refresh", "000-api-key:rotation"])},
                             pattern_named="deploy")
    assert lineage3["generation"] == 3
    spec_dirs = [f["spec_dir"] for f in lineage3["features"]]
    assert any("sklearn-deploy-pipeline" in d for d in spec_dirs) and not any("sk-learn" in d for d in spec_dirs)
    assert validate(sdd_export, gen3, draft_from_lineage(lineage3, "my-tool")).code == 0
