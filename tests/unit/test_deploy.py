"""Unit tests for tools/deploy.py. Each section maps to a user story in spec.md."""

from __future__ import annotations

import json
import re

from conftest import DEFAULT_SOURCE, snapshot, write_tree


def manifest(env) -> dict:
    return json.loads((env.state / "manifest.json").read_text(encoding="utf-8"))


def installed_files(env) -> dict:
    return {k: v for k, v in snapshot(env.target).items() if not k.startswith(".claude-settings")}


# ------------------------------------------------------- US1: fresh install


def test_fresh_install_creates_every_file(env):
    code, out = env.run()

    assert code == 0
    for rel, content in DEFAULT_SOURCE.items():
        assert (env.target / rel).read_bytes() == content.encode("utf-8")
    assert sorted(l.split()[1] for l in env.lines(out, "created")) == sorted(DEFAULT_SOURCE)
    assert manifest(env)["status"] == "complete"
    assert sorted(e["path"] for e in manifest(env)["entries"]) == sorted(DEFAULT_SOURCE)


def test_install_creates_missing_target_directory(env):
    assert not env.target.exists()

    code, _ = env.run()

    assert code == 0
    assert (env.target / "CLAUDE.md").is_file()


def test_manifest_has_no_absolute_paths_or_personal_data(env):
    env.run()

    text = (env.state / "manifest.json").read_text(encoding="utf-8")
    assert str(env.home) not in text
    assert env.home.name not in text
    assert "\\" not in text
    assert "@" not in text
    for entry in manifest(env)["entries"]:
        assert not entry["path"].startswith("/")
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])


def test_gitkeep_is_not_deployed(env):
    write_tree(env.source, {"skills/.gitkeep": ""})

    env.run()

    assert not (env.target / "skills" / ".gitkeep").exists()


def test_unknown_argument_fails_without_writing(env):
    code, _ = env.run("--force")

    assert code == 1
    assert not env.target.exists()


def test_missing_source_fails_without_writing(env, tmp_path):
    env.source = tmp_path / "nowhere"

    code, _ = env.run()

    assert code == 1
    assert not env.target.exists()


# ------------------------------------------------------------- US2: update


def test_update_applies_changes_additions_and_removals(env):
    env.run()
    write_tree(env.source, {"CLAUDE.md": "# Changed\n", "skills/sdd-drive/SKILL.md": "drive\n"})
    (env.source / "skills" / "sdd-grill" / "SKILL.md").unlink()

    code, out = env.run()

    assert code == 0
    assert env.lines(out, "updated") == ["updated   CLAUDE.md"]
    assert env.lines(out, "created") == ["created   skills/sdd-drive/SKILL.md"]
    assert env.lines(out, "deleted") == ["deleted   skills/sdd-grill/SKILL.md"]
    assert (env.target / "CLAUDE.md").read_text(encoding="utf-8") == "# Changed\n"
    assert not (env.target / "skills" / "sdd-grill").exists()
    paths = [e["path"] for e in manifest(env)["entries"]]
    assert "skills/sdd-grill/SKILL.md" not in paths
    assert "skills/sdd-drive/SKILL.md" in paths


def test_repeated_runs_change_nothing(env):
    env.run()
    before = snapshot(env.target, with_mtime=True)

    for _ in range(10):
        code, out = env.run()
        assert code == 0
        assert out.strip() == "Already up to date."

    assert snapshot(env.target, with_mtime=True) == before


def test_interrupted_run_converges(env):
    env.run()
    write_tree(env.source, {"CLAUDE.md": "# v2\n", "skills/sdd-init/SKILL.md": "v2\n"})
    # Simulate a crash after the journal and the first file were written.
    data = manifest(env)
    data["status"] = "applying"
    for entry in data["entries"]:
        if entry["path"] in ("CLAUDE.md", "skills/sdd-init/SKILL.md"):
            entry["previous"] = entry["sha256"]
            entry["sha256"] = env.deploy.sha256_bytes((env.source / entry["path"]).read_bytes())
    (env.state / "manifest.json").write_bytes(json.dumps(data).encode("utf-8"))
    (env.target / "CLAUDE.md").write_bytes(b"# v2\n")

    code, out = env.run()

    assert code == 0
    assert not env.lines(out, "conflict")
    assert (env.target / "skills" / "sdd-init" / "SKILL.md").read_text(encoding="utf-8") == "v2\n"
    assert manifest(env)["status"] == "complete"
    assert all("previous" not in e for e in manifest(env)["entries"])
    assert env.run()[1].strip() == "Already up to date."


# ---------------------------------------------------- US3: protect existing


def test_foreign_file_blocks_everything(env):
    write_tree(env.target, {"CLAUDE.md": "mine\n", "notes.txt": "keep me\n"})
    before = snapshot(env.target, with_mtime=True)

    code, out = env.run()

    assert code == 2
    assert env.lines(out, "conflict") == ["conflict  CLAUDE.md (not installed by this tool)"]
    assert "Nothing was written" in out
    assert snapshot(env.target, with_mtime=True) == before


def test_all_conflicts_are_listed_at_once(env):
    write_tree(env.target, {"CLAUDE.md": "mine\n", "skills/sdd-init/SKILL.md": "mine too\n"})

    code, out = env.run()

    assert code == 2
    assert len(env.lines(out, "conflict")) == 2


def test_manual_edit_blocks_update(env):
    env.run()
    (env.target / "CLAUDE.md").write_text("edited by hand\n", encoding="utf-8")
    write_tree(env.source, {"skills/sdd-init/SKILL.md": "new version\n"})
    before = snapshot(env.target, with_mtime=True)

    code, out = env.run()

    assert code == 2
    assert env.lines(out, "conflict") == ["conflict  CLAUDE.md (modified since install)"]
    assert snapshot(env.target, with_mtime=True) == before


def test_manual_edit_blocks_even_without_source_changes(env):
    env.run()
    (env.target / "CLAUDE.md").write_text("edited by hand\n", encoding="utf-8")

    code, _ = env.run()

    assert code == 2


def test_replace_backs_up_foreign_file(env):
    write_tree(env.target, {"CLAUDE.md": "mine\n"})

    code, out = env.run("--replace")

    assert code == 0
    assert (env.state / "backups" / "CLAUDE.md").read_text(encoding="utf-8") == "mine\n"
    assert (env.target / "CLAUDE.md").read_text(encoding="utf-8") == DEFAULT_SOURCE["CLAUDE.md"]
    assert env.lines(out, "backup") == ["backup    CLAUDE.md -> .claude-settings/backups/CLAUDE.md"]
    entry = next(e for e in manifest(env)["entries"] if e["path"] == "CLAUDE.md")
    assert entry["backup"] is True


def test_replace_sets_aside_manual_edit_and_keeps_first_backup(env):
    write_tree(env.target, {"CLAUDE.md": "original\n"})
    env.run("--replace")
    (env.target / "CLAUDE.md").write_text("edited by hand\n", encoding="utf-8")

    code, out = env.run("--replace")

    assert code == 0
    assert (env.state / "backups" / "CLAUDE.md").read_text(encoding="utf-8") == "original\n"
    discarded = list((env.state / "discarded").rglob("CLAUDE.md"))
    assert len(discarded) == 1
    assert discarded[0].read_text(encoding="utf-8") == "edited by hand\n"
    assert len(env.lines(out, "discarded")) == 1
    assert (env.target / "CLAUDE.md").read_text(encoding="utf-8") == DEFAULT_SOURCE["CLAUDE.md"]


def test_identical_existing_file_is_adopted_without_backup(env):
    write_tree(env.target, {"CLAUDE.md": DEFAULT_SOURCE["CLAUDE.md"]})

    code, out = env.run()

    assert code == 0
    assert env.lines(out, "adopted") == ["adopted   CLAUDE.md"]
    assert not (env.state / "backups").exists()
    assert "CLAUDE.md" in [e["path"] for e in manifest(env)["entries"]]


def test_lost_manifest_treats_files_as_foreign(env):
    env.run()
    (env.state / "manifest.json").unlink()
    write_tree(env.source, {"CLAUDE.md": "# Changed\n"})

    code, out = env.run()

    assert code == 2
    assert env.lines(out, "conflict") == ["conflict  CLAUDE.md (not installed by this tool)"]


def test_corrupt_manifest_treats_files_as_foreign(env):
    env.run()
    (env.state / "manifest.json").write_text("{not json", encoding="utf-8")
    write_tree(env.source, {"CLAUDE.md": "# Changed\n"})

    code, _ = env.run()

    assert code == 2


# ------------------------------------------------------------- US4: remove


def test_install_then_remove_restores_everything(env):
    write_tree(env.target, {"CLAUDE.md": "original\n", "settings.json": "{}\n", "skills/other/SKILL.md": "x\n"})
    before = snapshot(env.target)

    assert env.run("--replace")[0] == 0
    code, out = env.run("remove")

    assert code == 0
    assert env.lines(out, "restored") == ["restored  CLAUDE.md"]
    assert snapshot(env.target) == before
    assert not env.state.exists()


def test_remove_after_fresh_install_leaves_no_trace(env):
    env.run()

    code, _ = env.run("remove")

    assert code == 0
    assert not env.target.exists()


def test_remove_keeps_unrelated_content(env):
    write_tree(env.target, {"settings.json": "{}\n"})
    env.run()

    env.run("remove")

    assert snapshot(env.target) == {"settings.json": b"{}\n"}


def test_remove_when_never_installed_changes_nothing(env):
    write_tree(env.target, {"CLAUDE.md": "mine\n"})
    before = snapshot(env.target, with_mtime=True)

    code, out = env.run("remove")

    assert code == 0
    assert out.strip() == "Nothing to remove."
    assert snapshot(env.target, with_mtime=True) == before


def test_remove_blocked_by_manual_edit(env):
    env.run()
    (env.target / "CLAUDE.md").write_text("edited by hand\n", encoding="utf-8")
    before = snapshot(env.target, with_mtime=True)

    code, out = env.run("remove")

    assert code == 2
    assert env.lines(out, "conflict") == ["conflict  CLAUDE.md (modified since install)"]
    assert snapshot(env.target, with_mtime=True) == before


def test_remove_replace_keeps_modified_file_in_discarded(env):
    env.run()
    (env.target / "CLAUDE.md").write_text("edited by hand\n", encoding="utf-8")

    code, out = env.run("remove", "--replace")

    assert code == 0
    assert installed_files(env) == {}
    discarded = list((env.state / "discarded").rglob("CLAUDE.md"))
    assert [d.read_text(encoding="utf-8") for d in discarded] == ["edited by hand\n"]
    assert not (env.state / "manifest.json").exists()
    assert "discarded" in out.splitlines()[-1]


def test_remove_ignores_files_already_deleted_by_hand(env):
    env.run()
    (env.target / "CLAUDE.md").unlink()

    code, out = env.run("remove")

    assert code == 0
    assert not env.lines(out, "conflict")
    assert not env.target.exists()


# ------------------------------------------------------------------ polish


def test_output_is_platform_neutral(env):
    write_tree(env.target, {"CLAUDE.md": "mine\n"})
    outputs = [env.run()[1], env.run("--replace")[1], env.run("remove")[1]]

    for out in outputs:
        assert "\\" not in out
        assert str(env.home) not in out
