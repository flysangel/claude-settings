"""Structure and content tests for home/skills/sdd-export/.

The contract is specs/006-sdd-export/contracts/skill.md. The checks look for the meaning of each required
instruction (key words, and the order of sections); they prove that the instructions are present, not that
Claude follows them, and they do not pin down wording.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = REPO_ROOT / "home" / "skills" / "sdd-export"
SKILL_MD = SKILL_DIR / "SKILL.md"
README_MD = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "sdd_export.py"
CLI_MD = REPO_ROOT / "specs" / "006-sdd-export" / "contracts" / "cli.md"

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
    for other in ("sdd_init", "sdd_update", "sdd_grill", "skills/sdd-"):
        assert other not in script


def test_script_runs_only_git():
    script = text(SCRIPT)

    assert re.findall(r'subprocess\.run\(\s*\[\s*"(\w+)"', script) == ["git"]
    assert "os.system" not in script and "Popen" not in script


def test_script_is_english_without_paths_or_emails():
    script = text(SCRIPT)

    assert not CJK.search(script)
    assert not ABSOLUTE_PATH.search(script)
    assert not EMAIL.search(script)


DELETE_CALLS = re.compile(r"(?:\bos\.|\bshutil\.|\.)(unlink|remove|rmtree|rmdir|removedirs|truncate)\(")


def function_of_each_line(source: str) -> dict[int, str]:
    tree = ast.parse(source)
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for line in range(node.lineno, node.end_lineno + 1):
                # innermost function wins: walk visits outer functions first
                owner[line] = node.name
    return owner


def test_script_deletes_only_its_own_temporary_files_and_new_empty_folder():
    source = text(SCRIPT)
    owner = function_of_each_line(source)
    found = []
    for number, line in enumerate(source.split("\n"), start=1):
        code = line.split("#", 1)[0]
        for match in DELETE_CALLS.finditer(code):
            found.append((match.group(1), owner.get(number)))

    assert "rmtree" not in source and "removedirs" not in source and "truncate(" not in source
    assert found, "write must clean up its temporary files"
    for name, function in found:
        assert name in ("unlink", "rmdir"), name
        assert function in ("cleanup_after_failure",), (name, function)


# ------------------------------------------------------------- SKILL.md
# (added with the instructions they check)

CONTRACT_MD = REPO_ROOT / "specs" / "006-sdd-export" / "contracts" / "skill.md"
DATA_MODEL_MD = REPO_ROOT / "specs" / "006-sdd-export" / "data-model.md"

SCRIPT_CALL = 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py"'
CHECK = SCRIPT_CALL + " check"
FILES = SCRIPT_CALL + " files"
VALIDATE = SCRIPT_CALL + " validate"
WRITE = SCRIPT_CALL + " write --expect"

RULES = "Rules for the whole run"
STAGES = {
    1: "Stage 1: Start",
    2: "Stage 2: Scope",
    3: "Stage 3: Reading",
    4: "Stage 4: Building the draft",
    5: "Stage 5: Presenting and deciding",
    6: "Stage 6: Validating",
    7: "Stage 7: Final confirmation",
    8: "Stage 8: Writing",
    9: "Stage 9: Final report",
}
DRAFT = "The draft"


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
    """Second-level heading -> its text, lowercased with whitespace collapsed, in document order."""
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


def stage(number: int) -> str:
    return section(STAGES[number])


def flat_body() -> str:
    return " ".join(body().split()).lower()


def flat_instructions() -> str:
    """The body from the first second-level heading on: without the overview of the commands at the top."""
    content = flat_body()
    return content[content.index("## "):]


def has_all(haystack: str, *needles: str) -> None:
    for needle in needles:
        assert needle.lower() in haystack, f"missing: {needle!r}"


def has_any(haystack: str, *needles: str) -> None:
    assert any(n.lower() in haystack for n in needles), f"none of {needles!r}"


def part(haystack: str, start: str, end: str | None = None) -> str:
    """The text from the first occurrence of start (lowercase) to the next occurrence of end."""
    begin = haystack.index(start.lower())
    if end is None:
        return haystack[begin:]
    return haystack[begin : haystack.index(end.lower(), begin + len(start))]


# ------------------------------------------------------------ frontmatter


def test_skill_frontmatter():
    fields, _ = split_frontmatter(text(SKILL_MD))

    assert sorted(fields) == ["argument-hint", "description", "disable-model-invocation", "name"]
    assert fields["name"] == "sdd-export"
    assert fields["disable-model-invocation"] == "true"
    assert fields["argument-hint"] == '"[scope path ...]"'
    description = fields["description"].strip('"')
    assert description and not CJK.search(description)
    lowered = description.lower()
    has_all(lowered, "old project", ".sdd-export/", "/sdd-rebuild", "spec kit", "lessons", "generation")
    has_any(lowered, "nutrients")
    has_any(lowered, "requirements")
    has_any(lowered, "does not need spec kit", "without spec kit", "no spec kit")
    has_any(lowered, "until the maintainer confirms", "before the maintainer confirms", "until you confirm")


def test_skill_body_is_english_without_paths_or_emails():
    content = body()

    assert not CJK.search(content)
    assert not ABSOLUTE_PATH.search(content)
    assert not EMAIL.search(content)


def test_sections_are_in_order():
    names = list(sections())
    expected = [RULES, DRAFT] + list(STAGES.values())
    present = [n for n in names if n in expected]

    assert present == expected, names


def test_every_script_call_uses_the_skill_dir_and_no_project_option():
    content = body()
    calls = re.findall(r"uv run [^\n`]*sdd_export\.py[^\n`]*", content)

    assert calls
    for call in calls:
        assert call.startswith(SCRIPT_CALL), call
        assert "--project" not in call, call


# -------------------------------------------- rules for the whole run


def test_rule_1_read_only():
    rules = section(RULES)

    has_all(rules, "read-only", "read", "grep", "glob", "files", "build", "test", "stdin")
    has_all(rules, "git --no-pager log", "show", "ls-files", "blame")
    has_any(rules, "install", "installing")
    has_any(rules, "format")
    has_any(rules, "project's own scripts", "scripts of the project", "project's scripts")
    has_any(rules, "temporary file", "temp file")
    has_all(rules, "write", "edit")


def test_rule_2_the_only_write():
    rules = section(RULES)

    has_all(rules, ".sdd-export/", "write")
    has_any(rules, "only write", "only thing that writes", "the one write", "only change")


def test_rule_3_no_spec_kit():
    rules = section(RULES)

    has_all(rules, "speckit-", "/sdd-init")
    has_any(rules, "never call", "do not call", "do not invoke", "never invoke")
    has_any(rules, "do not ask", "never ask", "do not suggest", "never suggest")
    has_all(rules, ".specify/memory/constitution.md", "specs/")


def test_spec_kit_names_appear_only_to_say_they_are_not_used():
    content = flat_body()
    for name in ("speckit-", "/sdd-init"):
        for match in re.finditer(re.escape(name), content):
            window = content[max(0, match.start() - 160) : match.end() + 40]
            assert re.search(r"\b(never|not|no)\b", window), window


def test_rule_4_secrets():
    rules = section(RULES)

    has_all(rules, "secret_files", "secret_hits")
    has_any(rules, "never open", "do not open", "do not read")
    has_any(rules, "quote", "repeat")
    has_any(rules, "location", "path and line")


def test_rule_5_questions():
    rules = section(RULES)

    has_all(rules, "askuserquestion", "recommend", "first", "one decision")
    has_any(rules, "reason", "why")
    has_any(rules, "multiselect", "multi-select", "several answers", "select several")
    has_any(rules, "one doubt per question", "one question per doubt", "each doubt gets its own question")
    has_any(rules, "not available", "unavailable", "cannot be used")
    has_any(rules, "plain text", "in text")


def test_rule_6_language():
    rules = section(RULES)

    has_all(rules, "traditional chinese", "must", "should")
    has_any(rules, "translate")
    has_any(rules, "conversation", "talk")


def test_rule_7_stopping_before_confirmation():
    rules = section(RULES)

    has_all(rules, "nothing is saved", "/sdd-export")
    has_any(rules, "start over", "starts over", "start again", "from the beginning")
    has_any(rules, "at any stage", "any stage", "at any point")


def test_rule_8_changing_an_earlier_decision():
    rules = section(RULES)

    has_any(rules, "changes an earlier decision", "changes their mind", "changes a decision")
    has_any(rules, "update the draft", "change the draft", "change that item")
    has_any(rules, "do not reopen", "without reopening", "do not discuss the other", "do not go through the other")


def test_rule_9_no_commits():
    rules = section(RULES)

    has_all(rules, "git add", "git commit", "git push", "commit")
    has_any(rules, ".git/")


def test_rule_10_nothing_made_up():
    rules = section(RULES)

    has_all(rules, "pending")
    has_any(rules, "never invent", "do not invent", "never make up", "do not make up")


# ------------------------------------------------------------- the draft


def test_draft_reference_lists_the_shape():
    draft = section(DRAFT)

    for key in ("generation", "project", "language", "scope", "coverage", "included", "principles", "features",
                "requirements", "lessons", "discarded", "id", "origin", "revised", "derived_from", "status", "evidence",
                "depends_on", "spec", "summary", "discarded_in", "reason"):
        assert f"`{key}`" in draft, key
    for value in ("story", "functional", "edge-case", "success-criterion", "assumption", "decision", "pitfall",
                  "reversed", "doubt", "confirmed", "pending", "constitution", "mixed", "maintainer", "commit:"):
        assert value in draft, value
    has_all(draft, "tool", "schema", "exported_at", '"zh-hant"')
    has_any(draft, "leave out", "do not include", "never include")
    has_any(draft, "code block", "code blocks")


# ---------------------------------------------------------------- stage 1


def test_check_is_the_first_action():
    content = flat_instructions()
    content = content[content.index("## " + STAGES[1].lower()):]
    first = content.index(CHECK.lower())

    assert CHECK.lower() in stage(1)
    for later in (FILES, VALIDATE, WRITE):
        assert first < content.index(later.lower())
    has_any(stage(1), "first thing", "before anything else", "first action", "before you read")
    has_any(stage(1), "before reading any file", "before you read any file", "before reading any project file",
            "before you read any project file", "before you open any project file")


STAGE_1_FAILURES = {
    "conflict": ("conflicts", "move", "rename"),
    "nutrients-unreadable": ("errors",),
    "nutrients-invalid": ("errors",),
    "nutrients-newer": ("update",),
    "lineage-newer": ("update",),
    "lineage-unreadable": ("first generation",),
    "lineage-invalid": ("first generation",),
    "lineage-conflict": ("first generation",),
}


def raw_section(name: str) -> list[str]:
    lines, inside = [], False
    for line in body().split("\n"):
        if line.startswith("## "):
            inside = line[3:].strip() == name
        elif inside:
            lines.append(line)
    return lines


def list_item(name: str, token: str) -> str:
    """The first top-level list item of a section (with its continuation lines) that mentions token, lowercased."""
    items: list[list[str]] = []
    for line in raw_section(name):
        if line.startswith("- "):
            items.append([line])
        elif items and (line.startswith("  ") or not line.strip()) and items[-1] is not None:
            items[-1].append(line)
        elif items:
            items.append(None)
    for item in items:
        if item and token.lower() in " ".join(item).lower():
            return " ".join(" ".join(item).split()).lower()
    raise AssertionError(f"no list item in '{name}' mentions {token!r}")


def stage_1_branch(reason: str) -> str:
    return list_item(STAGES[1], f"`{reason}`")


@pytest.mark.parametrize("reason", sorted(STAGE_1_FAILURES))
def test_stage_1_failures_stop_without_overwriting(reason):
    one = stage(1)
    assert f"`{reason}`" in one, reason
    branch = stage_1_branch(reason)

    has_any(branch, "stop")
    has_any(branch, "nothing was written", "nothing has been written", "nothing is written", "wrote nothing")
    has_any(branch, "overwrite", "not overwrit", "never overwrit")
    for needle in STAGE_1_FAILURES[reason]:
        assert needle in branch, (reason, needle)


def test_stage_1_handles_uv_and_unexpected_results():
    one = stage(1)

    has_all(one, "uv")
    has_any(one, "install", "installed")
    has_any(one, "any other reason", "another reason", "unexpected")


def test_stage_1_successful_results():
    one = stage(1)

    has_all(one, "inventory.files", "skipped", "writable", "existing_generation", "generation")
    has_all(one, '"edited"', '"unknown"', "lineage", '"none"', "first generation")
    has_any(one, "stage 2")
    writable = list_item(STAGES[1], "`writable` is")
    has_all(writable, "askuserquestion", "continue", "stop")
    has_any(writable, "may fail", "might fail", "may not be able")
    mismatch = list_item(STAGES[1], "`existing_generation` is")
    has_all(mismatch, "stop", "continue", "copied", "removed")
    edited = list_item(STAGES[1], '`"edited"`')
    has_any(edited, "maintainer's decision", "maintainer's decisions", "decisions of the maintainer")


def test_stage_1_order_of_the_success_checks():
    one = stage(1)

    files = one.index("`inventory.files`")
    assert files < one.index("`writable`") < one.index("`existing_generation`")


# ---------------------------------------------------------------- stage 2


def test_stage_2_scope():
    two = stage(2)

    has_all(two, "--scope", "too_large", "areas", "askuserquestion", "partial", "included", "/sdd-export")
    has_any(two, "multiselect", "multi-select", "several")
    has_any(two, "do not read", "before reading", "not open")
    has_any(two, "kept as they are", "stay as they are", "left as they are", "kept unchanged")


def test_stage_2_results():
    two = stage(2)

    has_all(two, '"usage"', "stage 3")
    has_any(two, "still too large", "still `true`", "is still too large")
    has_any(two, "batch", "batches")
    has_any(two, "refuses", "does not want to narrow", "will not narrow", "declines")
    has_all(two, "nothing is saved")


def test_scope_comes_before_reading():
    content = flat_instructions()

    assert content.index("## " + STAGES[2].lower()) < content.index("## " + STAGES[3].lower())
    assert content.index("--scope") < content.index("## " + STAGES[3].lower())


# ---------------------------------------------------------------- stage 3


def test_stage_3_reading():
    three = stage(3)

    has_all(three, "files", "constitution", "specs", "secret_files", "mixed", "evidence", "pending")
    has_any(three, "actually does", "currently does", "current behaviour", "current behavior")
    has_any(three, "not how it is implemented", "not the implementation", "never how", "not describe how")
    has_any(three, "doubt", "doubts")
    has_any(three, "suspected bug", "looks like a bug", "possible bug")
    has_all(three, "both")
    has_all(three, "plan", "tasks")
    has_any(three, "never copy", "do not copy", "not copied")


def test_stage_3_lessons():
    three = stage(3)

    has_all(three, "decision", "pitfall", "reversed", "commit:", "git --no-pager log", "pending")


def test_stage_3_results():
    three = stage(3)

    has_all(three, "stage 4", "stage 2", "nothing was written")
    has_any(three, "not enough", "too little", "insufficient")
    has_any(three, "cannot be read", "could not be read", "can't be read")
    has_any(three, "do not try another", "do not use another", "never use another", "do not switch to")
    has_any(three, "context", "cannot read everything", "too much to read")


# ---------------------------------------------------------------- stage 4


def test_stage_4_draft_rules():
    four = stage(4)

    has_all(four, "generation", "check", "existing", "lineage", "origin", "discarded", "revised")
    has_any(four, "do not compute", "never compute", "not compute")
    has_any(four, "new id", "new ids", "new `id`")
    has_any(four, "never repeat", "not repeat", "must not match", "not used before", "never reuse", "not reuse")


def test_stage_4_lineage():
    four = stage(4)

    has_all(four, "in_lineage", "lineage_missing_specs", "askuserquestion", "keep", "discard")
    has_any(four, "still apply", "still applies")
    has_any(four, "unchanged", "as they are", "exactly as")
    has_any(four, "silently", "disappear")


def test_stage_4_re_export():
    four = stage(4)

    has_all(four, "existing", "export_dir", "ours", '"edited"', '"unknown"')
    has_any(four, "starting point", "start from")
    has_any(four, "one by one", "item by item", "each change")
    has_any(four, "outside the scope", "outside this scope", "outside the chosen scope")


# ---------------------------------------------------------------- stage 5


def test_stage_5_presenting():
    five = stage(5)

    order = [five.index(word) for word in ("generation", "principles", "features", "doubts", "lessons")]
    assert order == sorted(order), order
    has_all(five, "pending", "doubt", "discarded", "maintainer", "source", "evidence")
    has_any(five, "short list", "brief list", "short summary")
    has_any(five, "one question per doubt", "one doubt per question", "own question")


def test_stage_5_lessons_without_evidence():
    five = stage(5)
    lessons = part(five, "no lesson", None) if "no lesson" in five else part(five, "found no", None)

    has_all(lessons, "maintainer", "askuserquestion")
    has_any(lessons, "invent", "make up")
    has_any(lessons, "empty", "`lessons` stays", "no lessons")


def test_stage_5_results():
    five = stage(5)

    has_all(five, "stage 6", "nothing is saved")
    has_any(five, "adds a requirement", "wants to add", "adds an item", "adds something")
    has_any(five, "earlier section", "already decided")


def test_nothing_is_written_before_stage_8():
    content = flat_instructions()
    stage_8 = content.index("## " + STAGES[8].lower())

    assert content.index(WRITE.lower()) > stage_8
    has_any(stage(5), "nothing is written", "do not write", "never write")


# ---------------------------------------------------------------- stage 6


def test_stage_6_validate():
    six = stage(6)

    assert VALIDATE.lower() in six
    for name in ('"secret"', '"invalid"', "field", "id", "range", "code-block", "dependency", "scope", "spec", "json",
                 "unsupported", "evidence", "lineage-item-missing", "origin-changed", "origin-unknown",
                 "revision-unmarked", "discard-lost", "discarded-active", "derived-unknown", "id-reused", "generation",
                 "exit code 3", "stage 1", "stage 7"):
        assert name in six, name
    secret = part(six, '"secret"', '"invalid"')
    has_any(secret, "do not repeat", "never repeat", "without repeating")


def test_validate_comes_before_the_final_confirmation():
    content = flat_instructions()

    assert content.index(VALIDATE.lower()) < content.index("## " + STAGES[7].lower())


# ---------------------------------------------------------------- stage 7


def test_stage_7_confirmation():
    seven = stage(7)

    has_all(seven, "counts", "diff", "pending", "discarded", "askuserquestion", "confirm", "stage 8", "stage 5",
            "stage 6", "nothing is saved")
    has_any(seven, "no differences", "nothing changed", "no difference")
    view = part(seven, '"edited"', None)
    has_all(view, ".sdd-export/readme.md")
    has_any(view, "overwrite", "replace", "regenerat")


def test_confirmation_comes_before_write_and_write_before_the_report():
    content = flat_instructions()

    seven = content.index("## " + STAGES[7].lower())
    eight = content.index("## " + STAGES[8].lower())
    nine = content.index("## " + STAGES[9].lower())
    assert seven < content.index(WRITE.lower()) < nine
    assert eight < content.index(WRITE.lower())


# ---------------------------------------------------------------- stage 8


def test_stage_8_write():
    eight = stage(8)

    assert WRITE.lower() in eight
    has_all(eight, "state", "stdin", '"changed"', '"conflict"', '"os-error"', '"invalid"', '"secret"', "exit code 3",
            "stage 1", "stage 6", "stage 7", "stage 9", "retry", "askuserquestion", "conflicts")
    has_any(eight, "half-written", "half written", "partial file")
    has_any(eight, "whole confirmed draft", "full confirmed draft", "complete confirmed draft",
            "entire confirmed draft")


def test_stage_8_failures_show_the_draft():
    eight = stage(8)
    for reason in ('"conflict"', '"os-error"'):
        branch = list_item(STAGES[8], reason)
        has_any(branch, "confirmed draft", "draft in full", "whole draft")


def test_stage_8_retry_checks_again():
    eight = stage(8)
    retry = part(eight, "retry", None)

    assert CHECK.lower() in eight
    has_any(retry, "same `state`", "state is the same", "`state` is the same", "`state` is unchanged", "same state")


# ---------------------------------------------------------------- stage 9


def test_stage_9_report():
    nine = stage(9)

    has_all(nine, ".sdd-export/nutrients.json", ".sdd-export/readme.md", "/sdd-rebuild", "/sdd-export", "partial",
            "generation", "pending", "discarded", "commit", "stop")
    has_any(nine, "new project", "the new project")
    has_any(nine, "inherited", "carried over")
    has_any(nine, "changes their mind", "changes the mind", "wants to change something after")
    has_any(nine, "delete", "remove")
