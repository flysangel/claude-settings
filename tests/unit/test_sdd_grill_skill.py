"""Structure and content tests for home/skills/sdd-grill/.

The contract is specs/005-sdd-grill/contracts/skill.md. The checks look for key phrases and the order
of sections; they prove that the required instructions are present, not that Claude follows them.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = REPO_ROOT / "home" / "skills" / "sdd-grill"
SKILL_MD = SKILL_DIR / "SKILL.md"
README_MD = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "sdd_grill.py"

CJK = re.compile(r"[⺀-鿿가-힯豈-﫿＀-￯]")
ABSOLUTE_PATH = re.compile(r"(?<![\w$}\"'.-])(/home/|/Users/|/root/|/tmp/|/usr/|/etc/|~/|[A-Za-z]:\\)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def inline_metadata(script: str) -> dict:
    lines = script.split("\n")
    assert lines[0] == "# /// script"
    end = lines.index("# ///", 1)
    return tomllib.loads("\n".join(row[2:] for row in lines[1:end]))


# ------------------------------------------------------------------ script


def test_script_has_uv_inline_metadata():
    metadata = inline_metadata(text(SCRIPT))

    assert metadata["requires-python"] == ">=3.11"
    assert metadata["dependencies"] == []


def test_script_imports_only_the_standard_library():
    tree = ast.parse(text(SCRIPT))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])

    assert modules, "the script imports nothing?"
    assert modules <= set(sys.stdlib_module_names) | {"__future__"}, modules - set(sys.stdlib_module_names)


def test_script_loads_no_other_skill():
    script = text(SCRIPT)

    assert "spec_from_file_location" not in script
    assert "importlib" not in script
    for other in ("sdd_init", "sdd_update", "skills/sdd-"):
        assert other not in script


def test_script_runs_only_git():
    script = text(SCRIPT)

    assert re.findall(r'subprocess\.run\(\s*\[\s*"(\w+)"', script) == ["git"]


def test_script_is_english_without_paths_or_emails():
    script = text(SCRIPT)

    assert not CJK.search(script)
    assert not ABSOLUTE_PATH.search(script)
    assert not EMAIL.search(script)


# ------------------------------------------------------------- SKILL.md

CHECK = 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" check'
SAVE = 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" save'
VERIFY = 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" verify'
FOCUS = 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" focus'
CLEAR = 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" clear'

# The second-level headings of SKILL.md, in order.
START = "Start"
RESUME = "Resume"
RULES = "Rules for questioning"
ORDER = "Order of the discussion"
SAVING = "Saving progress"
SUMMARY = "Summary and confirmation"
GENERATE = "Generating the documents"
FAILURE = "When something fails"
FINISH = "Finishing"


def split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    lines = content.split("\n")
    assert lines[0] == "---"
    end = lines.index("---", 1)
    fields = {}
    for row in lines[1:end]:
        key, _, value = row.partition(":")
        fields[key.strip()] = value.strip()
    return fields, "\n".join(lines[end + 1 :])


def body() -> str:
    return split_frontmatter(text(SKILL_MD))[1]


def sections() -> dict[str, str]:
    """Second-level heading -> its text (lowercased, with lines joined), in document order."""
    result: dict[str, list[str]] = {}
    current = None
    for line in body().split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            assert current not in result, f"duplicate heading {current}"
            result[current] = []
        elif current is not None:
            result[current].append(line)
    return {name: " ".join(" ".join(lines).split()).lower() for name, lines in result.items()}


def section(name: str) -> str:
    found = sections()
    assert name in found, f"SKILL.md has no '## {name}' section; it has {list(found)}"
    return found[name]


def has_all(haystack: str, *needles: str) -> None:
    for needle in needles:
        assert needle.lower() in haystack, f"missing: {needle!r}"


def has_any(haystack: str, *needles: str) -> None:
    assert any(n.lower() in haystack for n in needles), f"none of {needles!r}"


def test_skill_frontmatter():
    fields, _ = split_frontmatter(text(SKILL_MD))

    assert sorted(fields) == ["argument-hint", "description", "name"]
    assert fields["name"] == "sdd-grill"
    assert fields["argument-hint"] == '"<requirement description>"'
    description = fields["description"].strip('"')
    assert description and not CJK.search(description)
    lowered = description.lower()
    has_all(lowered, "one decision at a time", "constitution", "spec", "spec kit")
    has_all(lowered, "use when", "not for")
    has_any(lowered, "new project", "new requirement")
    has_any(lowered, "unclear", "unsure", "undecided")
    has_any(lowered, "technology choice", "technology choices")
    has_any(lowered, "implementing an existing spec", "implement an existing spec")


def test_skill_body_is_english_without_paths_or_emails():
    content = body()

    assert not CJK.search(content)
    assert not ABSOLUTE_PATH.search(content)
    assert not EMAIL.search(content)


def test_skill_sections_are_in_order():
    names = list(sections())
    expected = [START, RESUME, RULES, ORDER, SAVING, SUMMARY, GENERATE, FAILURE, FINISH]
    present = [n for n in names if n in expected]

    assert present == [n for n in expected if n in present]
    for name in (START, RULES, ORDER, SAVING):
        assert name in present, name


def test_start_asks_for_a_requirement_first():
    start = section(START)

    has_all(start, "requirement")
    has_any(start, "no requirement", "without a requirement", "did not give a requirement")
    has_any(start, "do nothing else", "nothing else until")


def test_check_runs_before_any_question():
    content = body()

    assert CHECK in content
    first_check = content.index(CHECK)
    assert first_check < content.index("AskUserQuestion")
    assert first_check < content.index("## " + RULES)
    assert CHECK.lower() in section(START)


def test_start_handles_exit_code_3():
    start = section(START)

    has_all(start, "exit code 3", '"missing"', '"incomplete"', "/sdd-init", ".specify/", "`missing`", "stop")
    has_any(start, "do not run `/sdd-init` yourself", "never run `/sdd-init` yourself", "do not run /sdd-init yourself")
    has_any(start, "speckit-*")
    has_any(start, "do not create or change", "never create or change", "do not create or modify")
    has_any(start, "`uv` is not installed", "`uv` is missing", "uv is not installed", "`uv` is not available")


def test_start_handles_conflict_and_unreadable_progress():
    start = section(START)

    has_all(start, '"conflict"', '"unreadable"', "clear")


def test_rules_for_questioning():
    rules = section(RULES)

    # FR-004: find out what the project already says.
    has_all(rules, "constitution", "readme")
    has_any(rules, "do not ask", "don't ask", "instead of asking")
    # FR-002: questions come from the requirement and the project, no fixed list.
    has_any(rules, "fixed list", "fixed set", "question bank", "checklist of questions")
    # FR-003
    has_all(rules, "AskUserQuestion", "one question", "recommend", "first option", "reason")
    has_any(rules, "not available", "unavailable", "cannot be used")
    has_any(rules, "plain text", "in text")
    # FR-005
    has_any(rules, "vague", "ambiguous")
    # FR-006
    has_any(rules, "contradict", "conflicts with an earlier")
    has_all(rules, "both sides")
    has_any(rules, "amend the principle", "change the principle", "revise the principle")
    # FR-008
    has_all(rules, "for_plan")
    has_any(rules, "technology", "framework", "database")
    # FR-009
    has_any(rules, "secret", "password")
    has_any(rules, "never record", "do not record", "not record")
    # US3-2
    has_any(rules, "wants to stop", "asks to stop", "wants to end")
    has_all(rules, "summary")


def test_order_of_the_discussion():
    order = section(ORDER)

    principles = order.index("principles")
    feature_list = order.index("feature list")
    each = order.index("one feature at a time")
    assert principles < feature_list < each
    has_all(order, "depend", "scenario", "scope", "edge case")
    has_all(order, '"principles"', '"features"', '"feature"', '"summary"')
    # Item 16 and FR-020: the conversation follows the maintainer's settings; the documents follow the project.
    has_all(order, "talk with the maintainer", "existing documents", "traditional chinese", "must", "should")


def test_saving_progress():
    saving = section(SAVING)

    assert SAVE.lower() in saving
    has_all(saving, "stdin", "after every decision")
    has_any(saving, "fix", "correct")
    has_any(saving, "retry", "try again", "save again")
    has_all(saving, "secret", ".specify/sdd-grill/")
    has_any(saving, "only through `save`", "only through save", "only with `save`")


def test_summary_and_confirmation():
    summary = section(SUMMARY)

    has_all(summary, "decided", "deferred", "reason", "left for the plan", "order", "depend")
    has_all(summary, "one question", "confirm", "again")
    has_any(summary, "do not write or change", "must not write or change", "nothing is written to")
    has_all(summary, "constitution", "spec")


def test_generating_the_documents():
    generate = section(GENERATE)

    has_all(generate, '"confirmed"', "skill tool", "speckit-constitution", "speckit-specify")
    has_all(generate, "`keep`", "spec_dir", "assumptions", "one at a time", "clarif")
    has_any(generate, "do not infer", "not to infer", "must not infer")
    has_any(generate, "remove", "delete")
    has_all(generate, "ask the maintainer")
    has_any(generate, "never write the constitution or a spec by hand", "do not write the constitution or a spec by hand")
    has_any(generate, "never choose", "do not choose")
    has_all(generate, "number", "feature.json", "focus")
    assert generate.index("speckit-constitution") < generate.index("speckit-specify")


def test_going_back_to_discussing_only_before_any_document():
    generate = section(GENERATE)
    change = generate[generate.index("wants to change a decision after the summary was confirmed") :]

    has_all(change, '"discussing"', "nothing generated yet", "the constitution or a spec has been generated")
    has_all(change, "do not go back to", "baseline", "start over")
    assert change.index("nothing generated yet") < change.index("do not go back to")


def test_failure_keeps_the_progress_and_writes_nothing_more():
    failure = section(FAILURE)

    has_all(failure, "generated", "not generated", "progress", "stop", "verify", "focus", "clear")
    has_any(failure, "do not write the missing", "never write the missing", "do not fill in")
    has_any(failure, "do not delete", "never delete")


def test_failure_gives_a_way_out_of_failures_that_stay():
    failure = section(FAILURE)

    has_all(failure, "existing-spec-changed", "constitution-changed", "spec-missing", "lost its `spec.md`")
    has_all(failure, "restore", "start over", "/sdd-grill")
    has_any(failure, "go away by themselves", "go away on their own")
    assert failure.index("go away by themselves") < failure.index("existing-spec-changed")


def test_finishing():
    finish = section(FINISH)

    for command in (VERIFY, FOCUS, CLEAR):
        assert command.lower() in finish
    assert finish.index(VERIFY.lower()) < finish.index(FOCUS.lower()) < finish.index(CLEAR.lower())
    has_all(finish, "feature_directory", "feature.json", "/sdd-drive", "/speckit-plan", "depend", "order")
    has_all(finish, "stop", "plan", "tasks", "implement", "push")
    has_any(finish, "do not push", "never push")
    has_any(finish, "do not start", "never start")


def test_finishing_without_any_new_spec():
    finish = section(FINISH)
    without = finish[finish.index("when `feature_directory` is `null`") :]

    has_all(without, "no spec was generated", "left as it was", "created or amended", "/sdd-grill")
    has_any(without, "do not suggest `/sdd-drive`", "not suggest `/sdd-drive`")
    assert finish.index("when `feature_directory` is a folder") < finish.index("when `feature_directory` is `null`")


def test_order_allows_a_batch_without_features():
    order = section(ORDER)

    has_all(order, "`features` stays empty", "skip stage 3", "nothing to generate")


def test_summary_comes_before_generating_and_check_before_questions():
    content = body()

    assert content.index("## " + SUMMARY) < content.index("## " + GENERATE)
    assert content.index(CHECK) < content.index("## " + RULES)
    finishing = content.index("## " + FINISH)
    assert content.index(VERIFY, finishing) < content.index(FOCUS, finishing) < content.index(CLEAR, finishing)


def test_skill_never_edits_feature_json_itself():
    generate = section(GENERATE)

    has_any(
        generate,
        "never edit `.specify/feature.json` yourself",
        "do not edit `.specify/feature.json` yourself",
        "do not change `.specify/feature.json` yourself",
    )


def test_resume():
    resume = section(RESUME)

    has_all(resume, '"present"', "decided", "`changed`", "one question", "start over", CLEAR)
    has_all(resume, "constitution", "specs", "head")
    has_all(resume, "`stage`", "`current_feature`")
    has_any(resume, "do not ask about it again", "do not ask again", "never ask again", "do not ask about them again")
    has_all(resume, '"confirmed"', "not generated")
    has_any(resume, "do not reopen", "without reopening", "not reopen")


def confirmed_branch(resume: str) -> str:
    start = resume.index('if the `phase` is `"confirmed"`')
    return resume[start:]


def test_resume_confirmed_can_start_over_and_keeps_the_documents():
    confirmed = confirmed_branch(section(RESUME))

    has_all(confirmed, "verify", "continue", "start over", "stop", CLEAR, "unexpected")
    has_any(confirmed, "do not delete or undo", "never delete", "do not delete")
    has_all(confirmed, "step 5 of \"start\"")
    has_any(confirmed, "numbered after them", "after the existing ones")


def test_resume_confirmed_checks_a_written_constitution_again():
    confirmed = confirmed_branch(section(RESUME))

    has_all(confirmed, "did not report `constitution-not-written`", "rule by rule", "step 2 of \"generating the documents\"")
    assert confirmed.index("rule by rule") < confirmed.index("not generated yet; if none are missing")


def test_resume_confirmed_does_not_continue_over_lasting_failures():
    confirmed = confirmed_branch(section(RESUME))

    has_all(confirmed, "existing-spec-changed", "constitution-changed", "lost its `spec.md`")
    has_all(confirmed, "do not continue generating", "restore")


def test_resume_comes_after_start_and_before_the_rules():
    content = body()

    assert content.index("## " + START) < content.index("## " + RESUME) < content.index("## " + RULES)


def test_all_sections_are_present():
    names = list(sections())

    for name in (START, RESUME, RULES, ORDER, SAVING, SUMMARY, GENERATE, FAILURE, FINISH):
        assert name in names, name


def test_existing_project_instructions():
    rules, order, generate = section(RULES), section(ORDER), section(GENERATE)

    # Item 11 and US4-2: existing decisions are not asked again; conflicts with the constitution go to the maintainer.
    has_all(rules, "existing", "constitution", "specs")
    has_any(rules, "count as decided", "are already decided")
    has_any(rules, "amend the principle", "revise the principle")
    # Item 15: only conflicts and additions; keep or amend.
    has_all(order, "already has a constitution", "conflict")
    has_any(order, '"keep"', "`keep`")
    has_any(order, '"amend"', "`amend`")
    has_any(order, "only deal with", "only handle")
    has_all(order, "existing spec", "specs/")
    # Items 23 and 24: the constitution only changes when amended; existing specs are never overwritten.
    has_all(generate, "existing spec")
    has_any(generate, "never overwrite", "never overwritten", "do not overwrite", "not overwritten")
    has_any(generate, "after the existing ones", "after existing specs")


# ------------------------------------------------------- folder and README


def test_folder_holds_exactly_three_files():
    files = sorted(
        p.relative_to(SKILL_DIR).as_posix()
        for p in SKILL_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )

    assert files == ["README.md", "SKILL.md", "scripts/sdd_grill.py"]


def test_files_use_lf_line_endings():
    for path in (SKILL_MD, README_MD, SCRIPT):
        data = path.read_bytes()
        assert b"\r" not in data, path.name
        assert data.endswith(b"\n"), path.name


def test_readme_is_traditional_chinese_without_paths_or_emails():
    readme = text(README_MD)

    assert len(CJK.findall(readme)) > 200
    assert not ABSOLUTE_PATH.search(readme)
    assert not EMAIL.search(readme)


def test_readme_covers_usage_and_prerequisites():
    readme = text(README_MD)

    for needle in ("/sdd-grill", "Spec Kit", "/sdd-init", "uv", "git"):
        assert needle in readme, needle
    assert "主動" in readme  # Claude may use it on its own
    assert "非必要" in readme or "不是必要" in readme  # git is optional


def test_readme_covers_the_flow():
    readme = text(README_MD)

    principles, features, each = readme.index("原則"), readme.index("功能清單"), readme.index("逐一")
    assert principles < features < each
    for needle in ("確認", "speckit-constitution", "speckit-specify", "/sdd-drive"):
        assert needle in readme, needle


def test_readme_covers_the_progress():
    readme = text(README_MD)

    for needle in (".specify/sdd-grill/", ".gitignore", "清除", "保留", "機密", "HEAD", "未 commit"):
        assert needle in readme, needle


def test_readme_covers_feature_json_and_what_it_never_does():
    readme = text(README_MD)

    for needle in (".specify/feature.json", "編號最小", "不做的事", "覆蓋", "plan"):
        assert needle in readme, needle
