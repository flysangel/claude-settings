"""Structure and content checks for home/skills/sdd-drive/ (SKILL.md, README.md, the script's text).

The contract is specs/008-sdd-drive/contracts/skill.md. The checks look for keywords and the order of sections,
not for the full wording. They prove the instructions exist, not that Claude follows them (research.md D15).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from conftest import REPO_ROOT

SKILL_DIR = REPO_ROOT / "home" / "skills" / "sdd-drive"
SKILL_MD = SKILL_DIR / "SKILL.md"
README_MD = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "sdd_drive.py"

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿＀-￯]")
ABSOLUTE_PATH = re.compile(r"(?<![\w$}])(/home/|/Users/|/root/|[A-Za-z]:\\\\|~/\.claude)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def frontmatter() -> tuple[dict, str]:
    raw = text()
    assert raw.startswith("---\n")
    head, body = raw[4:].split("\n---\n", 1)
    fields = {}
    for line in head.splitlines():
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields, body


def sections() -> dict[str, str]:
    """'## ' headings -> their text (up to the next '## ')."""
    _, body = frontmatter()
    result = {}
    for part in re.split(r"(?m)^## ", body)[1:]:
        title, _, rest = part.partition("\n")
        result[title.strip()] = rest
    return result


def section(prefix: str) -> str:
    matches = [body for title, body in sections().items() if title.startswith(prefix)]
    assert len(matches) == 1, prefix
    return matches[0]


def rows(prefix: str) -> list[str]:
    """The table rows of a section (header and separator excluded)."""
    lines = [l for l in section(prefix).splitlines() if l.startswith("|")]
    return lines[2:]


def row(prefix: str, *keys: str) -> str:
    found = [r for r in rows(prefix) if all(k in r.split("|")[1] for k in keys)]
    assert len(found) == 1, (prefix, keys, len(found))
    return found[0]


def rule(number: int) -> str:
    general = section("General rules")
    match = re.search(rf"(?ms)^{number}\. (.*?)(?=^\d+\. |\Z)", general)
    assert match, number
    return " ".join(match.group(1).split())


# ============================================== T018 frontmatter, general rules 1-11, stage 1


def test_frontmatter_has_exactly_the_three_fields():
    fields, _ = frontmatter()
    assert list(fields) == ["name", "description", "disable-model-invocation"]
    assert fields["name"] == "sdd-drive"
    assert fields["disable-model-invocation"] == "true"
    description = fields["description"]
    assert not CJK.search(description)
    for word in ("plan", "tasks", "implement", "test", "check", "Spec Kit", "/sdd-drive", "approval"):
        assert word in description, word


def test_skill_md_is_english_without_paths_emails_or_orca():
    raw = text()
    assert not CJK.search(raw)
    assert not ABSOLUTE_PATH.search(raw)
    assert not EMAIL.search(raw)
    assert "orca" not in raw.lower()
    assert "SDD_DRIVE_CLAUDE" not in raw and "SDD_DRIVE_TEST_TIMING" not in raw and "`_drive`" not in raw and " _drive " not in raw


def test_script_is_run_through_uv_with_the_skill_dir():
    raw = text()
    assert 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_drive.py"' in raw
    for line in raw.splitlines():
        if "sdd_drive.py" in line and "uv run" in line:
            assert '"${CLAUDE_SKILL_DIR}/scripts/sdd_drive.py"' in line


@pytest.mark.parametrize("number,words", [
    (1, ["never run", "speckit-implement", "speckit-plan", "speckit-tasks", "speckit-converge", "do not take over"]),
    (2, ["status", "memory"]),
    (3, ["sdd-drive-state.json", ".specify/sdd-drive/", ".specify/feature.json", "claude"]),
    (4, ["run_in_background", "7200000", "watch", "end your turn"]),
    (5, ["do not ask"]),
    (6, ["never push"]),
    (7, ["uncommitted"]),
    (8, ["model", "reason", "sonnet", "opus", "fable", "strongest model", "next.model"]),
    (9, ["secret", "(not shown...)"]),
    (10, ["unexpected", "status", "stop"]),
    (11, ["language"]),
])
def test_general_rules(number, words):
    body = rule(number).lower()
    for word in words:
        assert word.lower() in body, (number, word)


def test_rule_8_does_not_use_the_strongest_model_for_everything():
    body = rule(8)
    assert "do not use the strongest model for every child" in body
    assert "plan `opus`" in body and "tasks `sonnet`" in body and "check (the convergence check) `opus`" in body


STAGE1_ROWS = [
    (("dependency",), True), (("speckit-missing",), True), (("speckit-incomplete",), True), (("no-specs",), True),
    (("claude-missing",), True), (("conflict",), True), (("state-unreadable",), True),
    (("running: true", "`running` or `resuming`"), False), (("running: true", "driver.phase: waiting"), False),
    (("only a launch",), False), (("last_attempt.auto",), False), (("next.action: finalize",), False),
    (("dirty",), True), (("next.action: none",), True), (("git: false",), False),
    (("`run`, `resume` or `test`",), False),
]


def test_stage_1_covers_the_16_results():
    assert len(rows("Stage 1")) == 16
    for keys, stops in STAGE1_ROWS:
        line = row("Stage 1", *keys)
        if stops:
            assert "stop" in line.lower(), keys
            cell = line.split("|")[2].lower().replace("do not start a child session", "")
            assert "start a child session" not in cell and "run `run" not in cell, keys


def test_stage_1_details():
    assert "missing" in row("Stage 1", "speckit-incomplete")
    assert "/sdd-init" in row("Stage 1", "speckit-missing")
    assert "Do not do the work yourself" in row("Stage 1", "claude-missing")
    assert "Do not delete" in row("Stage 1", "conflict")
    running = row("Stage 1", "running: true", "`running` or `resuming`")
    assert "do not `finalize`" in running and "Stage 3B" in running and "second child session" in running
    waiting = row("Stage 1", "driver.phase: waiting")
    assert "rule 13" in waiting and "cancel" in waiting and "Stage 3B" in waiting
    assert "Stage 3B" in row("Stage 1", "only a launch")
    assert "away" in row("Stage 1", "last_attempt.auto")
    assert "Stage 2" in row("Stage 1", "next.action: finalize")
    assert "Continue." in row("Stage 1", "git: false")
    announce = row("Stage 1", "`run`, `resume` or `test`")
    for word in ("Announce", "baseline: true", "no convergence check", "failure counts", "Stage 3", "Stage 4"):
        assert word in announce, word


def test_stage_1_order():
    order_line = next(l for l in section("Stage 1").splitlines() if l.startswith("Order:"))
    positions = [order_line.index(w) for w in ("run `status`", "table", "announce", "Stage 3 or Stage 4")]
    assert positions == sorted(positions)
    body = section("Stage 1")
    assert body.index("Order:") < body.index("| `status` result")


def test_skill_never_asks_the_main_session_to_do_the_work():
    raw = text()
    for sentence in re.split(r"(?<=[.!?])\s+", raw):
        lowered = sentence.lower()
        if re.search(r"\b(invoke|call|run)\b[^.]*\bspeckit-", lowered):
            assert "never" in lowered or "not" in lowered, sentence
        if re.search(r"\b(write|edit)\b[^.]*\b(plan|tasks|code)\b", lowered):
            assert "never" in lowered or "not" in lowered or "child" in lowered, sentence


# ============================================== T025 stage 3 skeleton and stage 3B


def test_stage_3_order_and_per_attempt_report():
    body = section("Stage 3:")
    order = ["run `status`", "rule 8", "run in the background", "--resume", "next.model", "wait for the notification",
             "read the output", "model_used"]
    positions = [body.index(word) for word in order]
    assert positions == sorted(positions)
    for word in ("spec", "phase", "`outcome`", "`auto`", "requested", "reason"):
        assert word in body.split("| `run` result")[0], word


STAGE3_ROWS = [
    ("phase: check", "converged"), ("outcome: failed",), ("outcome: verify-failed",),
    ("outcome: gaps-found",), ("status: waiting",), ("status: running",), ("status: launch-failed",),
    ("not-waitable",), ("already-auto",), ("auto_resume: cancelled",), ("skipped-changed",),
    ("auto: true", "`succeeded`"), ("auto: true", "something else"), ("outcome: api-error",),
    ("outcome: interrupted",), ("outcome: launch-failed",), ("resume_failed: true",), ("permission_denials",),
    ("reason: secret",), ("reason: running",), ("pending-finalize", "not-next"), ("reason: dirty",),
    ("branch-diverged",), ("speckit-missing", "state-unreadable"), ("os-error",), ("printed no JSON",),
    ("stopped by a usage limit",),
]


def test_stage_3_has_the_28_results():
    assert len(rows("Stage 3:")) == 28
    assert len([r for r in rows("Stage 3:") if r.split("|")[1].strip() == "`outcome: succeeded`"]) == 1
    for keys in STAGE3_ROWS:
        row("Stage 3:", *keys)


def test_stage_3_us1_rows():
    succeeded = [r for r in rows("Stage 3:") if r.split("|")[1].strip() == "`outcome: succeeded`"][0]
    assert "run `status` first" in succeeded and "Do not wait for approval" in succeeded
    assert "Stage 3B" in row("Stage 3:", "status: waiting")
    assert "Stage 3B" in row("Stage 3:", "status: running")
    assert "Stop." in row("Stage 3:", "status: launch-failed")
    assert "Stop." in row("Stage 3:", "outcome: launch-failed")
    assert "run once more" in row("Stage 3:", "reason: secret")
    running = row("Stage 3:", "reason: running")
    assert "Stop" in running and "do not `watch`" in running
    assert "Stage 1" in row("Stage 3:", "pending-finalize", "not-next")
    assert "Stage 1" in row("Stage 3:", "reason: dirty")
    assert "Do not merge or reset" in row("Stage 3:", "branch-diverged")
    assert "Same as Stage 1" in row("Stage 3:", "speckit-missing", "state-unreadable")
    assert "Stop." in row("Stage 3:", "os-error")
    assert "Stage 1" in row("Stage 3:", "printed no JSON")


def test_stage_3b():
    body = section("Stage 3B")
    assert "Stage 3 table" in body and "in the background" in body
    assert len(rows("Stage 3B")) == 3
    assert "Stage 1" in row("Stage 3B", "no-driver")
    assert "Stage 6" in row("Stage 3B", "cancel")
    assert "`watch` in the background again" in row("Stage 3B", "another message")


def test_stages_are_in_number_order():
    titles = list(sections())
    stage_titles = [t for t in titles if t.startswith("Stage")]
    assert [t.split(":")[0] for t in stage_titles] == ["Stage 1", "Stage 2", "Stage 3", "Stage 3B", "Stage 4",
                                                      "Stage 5", "Stage 6"]
    assert titles[0].startswith("General rules")


# ============================================== T029 stage 4 and the check rows


def test_stage_4_order_and_do_not_trust():
    body = section("Stage 4")
    order = ["run `status`", "`next.action` is `test`", "test --spec <next.spec>", "in the background",
             "follow the table"]
    positions = [body.index(word) for word in order]
    assert positions == sorted(positions)
    assert "do not trust" in body


def test_stage_4_has_the_6_results():
    assert len(rows("Stage 4")) == 6
    baseline = row("Stage 4", "passed: true", "baseline: true")
    assert "no convergence check" in baseline and "Stage 3 or Stage 4" in baseline
    other = row("Stage 4", "passed: true", "other specs")
    assert "next.phase: check" in other and "not done yet" in other
    failed = row("Stage 4", "passed: false")
    for word in ("Stop", "test command", "exit code", "output_tail", "failure count", "do not start any later spec"):
        assert word in failed, word
    assert "Stop." in row("Stage 4", "no-test-command") and "not treated as done" in row("Stage 4", "no-test-command")
    assert "Stage 3" in row("Stage 4", "pending-finalize", "dirty")
    assert "Stage 1" in row("Stage 4", "printed no JSON")


def test_stage_3_check_rows():
    gaps = row("Stage 3:", "outcome: gaps-found")
    for word in ("Stop the whole run", "do not fix anything", "do not start any later spec", "findings",
                 "source_ref", "gap_type", "findings_total", "over 50", "committed", "check failure count",
                 "first implements these tasks, then tests and checks again", "in tasks.md themselves",
                 "report-mismatch", "the file was used"):
        assert word in gaps, word
    converged = row("Stage 3:", "phase: check", "converged")
    assert "done" in converged and "next spec" in converged
    verify = row("Stage 3:", "outcome: verify-failed")
    for code in ("check-no-tasks", "check-rewrote-tasks", "check-touched-files"):
        assert code in verify, code


def test_rule_1_forbids_converge_and_rule_8_defaults_check_to_opus():
    assert "`speckit-converge`" in rule(1)
    assert "check (the convergence check) `opus`" in rule(8)


# ============================================== T037 stage 2, failure rows, stage 5


def test_stage_2_has_the_5_results():
    assert len(rows("Stage 2")) == 5
    lost = row("Stage 2", "lost")
    assert "rule 13" in lost and "Stop." in lost and "not counted as a failure" in lost
    other = row("Stage 2", "success (other)")
    for word in ("interrupted", "spec, phase, model and start time", "state_after", "resumes", "not counted as a failure",
                 "Stop."):
        assert word in other, word
    assert "Stop." in row("Stage 2", "reason: running")
    assert "Stage 1" in row("Stage 2", "nothing-to-finalize")
    assert "Rule 10" in row("Stage 2", "anything else")


def test_stage_3_failure_rows():
    failed = row("Stage 3:", "outcome: failed")
    for word in ("Stop the whole run", "do not start any later spec", "failure.kind", "failure.step",
                 "failure.reason", "failure count", "requirements", "spec or the constitution", "blocked-task",
                 "task IDs", "uncommitted changes", "retries this phase"):
        assert word in failed, word
    verify = row("Stage 3:", "outcome: verify-failed")
    for code in ("plan-missing", "tasks-missing", "tasks-unfinished", "tasks-removed", "protected-changed", "pushed",
                 "uncommitted"):
        assert f"`{code}`" in verify, code
    api = row("Stage 3:", "outcome: api-error")
    assert "detail.text" in api and "not counted as a failure" in api and "Stop" in api
    assert "Do not do the work yourself" in api
    interrupted = row("Stage 3:", "outcome: interrupted")
    assert "detail.code" in interrupted and "state_after" in interrupted and "not counted as a failure" in interrupted
    resume = row("Stage 3:", "resume_failed: true")
    assert "--resume --fresh" in resume and "once" in resume
    assert "denied tools" in row("Stage 3:", "permission_denials")


def test_stage_5_final_report():
    body = section("Stage 5")
    assert "final report" in body
    items = [" ".join(i.split()) for i in re.findall(r"(?ms)^\d\. (.*?)(?=^\d\. |^\S|\Z)", body)]
    assert len(items) == 4
    assert "state of every spec" in items[0]
    assert "Why it stopped" in items[1] and "not a failure" in items[1] and "rule 13" in items[1]
    assert "model_used" in items[2] and "reason" in items[2] and "findings" in items[2]
    assert "push" in items[3] and "CI on both platforms" in items[3] and "Notes" in items[3]
    assert "which spec, which step and why" in body


# ============================================== T045 rules 12-13, stage 6, usage-limit rows


def test_rule_12_automatic_resume_only_by_the_driver():
    body = rule(12).lower()
    for word in ("automatic resume", "once", "driver", "do not wait for a reset", "do not schedule a wake-up",
                 "`run --resume`", "stage 1", "`status`"):
        assert word.lower() in body, word
    assert "CronCreate" not in text()


def test_rule_13_usage_limit_report():
    body = rule(13)
    for word in ("not a failure", "not counted as a retry", "limit.types", "resets_at", "local time",
                 "no reset time", "state_after", "resume automatically", "/sdd-drive"):
        assert word in body, word


def test_stage_3_usage_limit_and_resume_rows():
    assert "rule 13" in row("Stage 3:", "status: waiting") and "cancel" in row("Stage 3:", "status: waiting")
    not_waitable = row("Stage 3:", "not-waitable")
    assert "rule 13" in not_waitable and "no reset time" in not_waitable and "Stop." in not_waitable
    assert "rule 13" in row("Stage 3:", "already-auto") and "Stop." in row("Stage 3:", "already-auto")
    assert "Stop." in row("Stage 3:", "auto_resume: cancelled")
    changed = row("Stage 3:", "skipped-changed")
    assert "dirty" in changed and "Stop." in changed
    assert "resumed automatically" in row("Stage 3:", "auto: true", "`succeeded`")
    assert "automatic resume" in row("Stage 3:", "auto: true", "something else")
    assert "--resume --fresh" in row("Stage 3:", "resume_failed: true")
    assert "Stage 1" in row("Stage 3:", "stopped by a usage limit") and "rule 12" in row("Stage 3:", "stopped by a usage limit")


def test_stage_6_cancel():
    body = section("Stage 6")
    assert "explicitly asks" in body and "`cancel`" in body
    assert len(rows("Stage 6")) == 3
    requested = row("Stage 6", "cancel_requested: true")
    assert "30 seconds" in requested and "watch" in requested and "auto_resume: cancelled" in requested
    assert "Stage 1" in row("Stage 6", "not-waiting")
    assert "Rule 10" in row("Stage 6", "anything else")


def test_stage_1_state_unreadable_offers_clear():
    line = row("Stage 1", "state-unreadable")
    for word in ("detail", "never a value", "baseline", "`clear`", "no spec is a baseline", "tested and checked",
                 "Never suggest deleting `.specify/sdd-drive/` by hand"):
        assert word in line, word


# ============================================== T052 folder, README and the script's text


def test_folder_holds_exactly_three_files():
    files = sorted(p.relative_to(SKILL_DIR).as_posix() for p in SKILL_DIR.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts)
    assert files == ["README.md", "SKILL.md", "scripts/sdd_drive.py"]
    tracked = subprocess.run(["git", "ls-files", "home/skills/sdd-drive"], cwd=REPO_ROOT, capture_output=True,
                             text=True).stdout.split()
    assert set(tracked) <= {"home/skills/sdd-drive/README.md", "home/skills/sdd-drive/SKILL.md",
                            "home/skills/sdd-drive/scripts/sdd_drive.py"}


def test_readme_is_traditional_chinese_and_covers_the_topics():
    readme = README_MD.read_text(encoding="utf-8")
    assert CJK.search(readme)
    for word in ("/sdd-drive", "disable-model-invocation", "plan", "tasks", "implement", "測試", "對照檢查", "停止",
                 "失敗", "漏做", "中斷", "用量上限", "沒有重置時間", "接續", "不 push", "分支", "疊在前一份之上",
                 ".specify/sdd-drive/", "不入庫", "claude -p", "uv", "模型", "opus", "sonnet", "既有的基準",
                 "不做對照檢查", "自動接續", "代價", "clear", "不要手動刪除", "Orca"):
        assert word in readme, word
    assert not ABSOLUTE_PATH.search(readme) and not EMAIL.search(readme)


def test_script_and_work_description_have_no_absolute_paths_or_emails():
    script = SCRIPT.read_text(encoding="utf-8")
    assert not ABSOLUTE_PATH.search(script)
    assert not EMAIL.search(script)
    templates = "".join(re.findall(r'(?s)BRIEF_[A-Z_]+ = (?:\{.*?\n\}|""".*?""")', script))
    assert "Project root: ." in templates
    assert not ABSOLUTE_PATH.search(templates) and not EMAIL.search(templates) and not CJK.search(templates)


# ============================================== T057 walkthrough findings


def test_resume_failed_takes_precedence_over_api_error_and_interrupted():
    assert "`resume_failed` is not `true`" in row("Stage 3:", "outcome: api-error")
    assert "`resume_failed` is not `true`" in row("Stage 3:", "outcome: interrupted")
    assert "whatever the `outcome`" in row("Stage 3:", "resume_failed: true")


def test_clear_after_state_unreadable_has_a_next_step():
    line = row("Stage 1", "state-unreadable")
    assert "run `clear`" in line and "go back to the start of Stage 1" in line and "report it and stop" in line


def test_cross_references_point_at_existing_stages():
    titles = [t.split(":")[0] for t in sections() if t.startswith("Stage")]
    for reference in set(re.findall(r"Stage (\d+B?)", text())):
        assert f"Stage {reference}" in titles, reference
    assert "Stage 3B" in row("Stage 6", "cancel_requested: true")
