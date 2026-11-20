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
    for other in ("sdd_init", "sdd_update", "sdd-init", "sdd-update"):
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
    # FR-020: language of the generated documents.
    has_all(order, "language", "traditional chinese", "must", "should")


def test_saving_progress():
    saving = section(SAVING)

    assert SAVE.lower() in saving
    has_all(saving, "stdin", "after every decision")
    has_any(saving, "fix", "correct")
    has_any(saving, "retry", "try again", "save again")
    has_all(saving, "secret", ".specify/sdd-grill/")
    has_any(saving, "only through `save`", "only through save", "only with `save`")
