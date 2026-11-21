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


# T059: the git commands and Grep searches that rule 1 allows never print the content of a file outside `files`.
GIT_ALLOWED = [
    "git --no-pager log --oneline -n <n> [-- <path>]",
    "git --no-pager log --stat -n <n> [<commit>] [-- <path>]",
    "git --no-pager ls-files",
    "git --no-pager blame -- <path>",
]
# Every git command SKILL.md writes out, placeholders or examples filled in, matches one of these.
GIT_FORMS = [
    re.compile(r"git --no-pager log --oneline -n (\d+|<n>)( \[?-- <path>\]?)?"),
    re.compile(r"git --no-pager log --stat -n (\d+|<n>)( \[?<(commit|hash)>\]?)?( \[?-- <path>\]?)?"),
    re.compile(r"git --no-pager ls-files"),
    re.compile(r"git --no-pager blame -- <path>"),
]


def git_commands() -> list[str]:
    """Every `git --no-pager ...` that SKILL.md writes out, up to the closing backtick or the end of the line."""
    return [match.group(0).strip() for line in body().split("\n")
            for match in re.finditer(r"git --no-pager [^`\n]*", line)]


def test_rule_1_lists_the_allowed_git_commands_exactly():
    raw = body()
    block = "\n".join("   " + line for line in GIT_ALLOWED)

    assert f"```text\n{block}\n   ```" in raw
    has_all(section(RULES), "exactly in these forms", "add no other option", "run no other git command")


def test_every_git_command_skill_md_writes_is_an_allowed_form():
    commands = git_commands()

    assert len(commands) >= len(GIT_ALLOWED)
    for command in commands:
        assert any(form.fullmatch(command) for form in GIT_FORMS), command
    assert "git --no-pager show" not in flat_body()


@pytest.mark.parametrize("printing", ["git show", "git diff", "git grep", "git cat-file", "git format-patch",
                                      "git stash show", "git whatchanged", "git reflog", "`-p`", "`--patch`", "`-u`",
                                      "`--patch-with-stat`", "`--cc`", "`-L`", "<commit>:<path>"])
def test_rule_1_forbids_git_that_prints_file_contents(printing):
    rules = section(RULES)
    window = rules[rules.index("add no other option"): rules.index("never run a build")]

    assert printing.lower() in window
    has_all(window, "secret files", "excluded folders")


def test_rule_1_keeps_grep_off_folders_and_blame_on_listed_files():
    rules = section(RULES)

    has_all(rules, "one path from `files` at a time", "never run grep on the project root or on a folder")
    has_all(rules, "never run `git blame` on a file that `files` does not list")


def test_rule_4_commit_messages_may_hold_secrets():
    rules = section(RULES)
    secrets = part(rules, "secrets stay out", "questions.")

    has_all(secrets, "commit messages", "never quote", "commit:<hash>", "doubt")


def test_stage_3_lessons_use_only_the_allowed_git_commands():
    three = stage(3)

    has_all(three, "only the git commands that rule 1 lists", "git --no-pager log --stat -n 1 <hash>",
            "never from a diff")


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


def test_stage_4_drops_by_where_an_item_is_not_by_its_origin():
    """T058: an item the rebuild created has origin equal to this generation and still goes to discarded."""
    four = stage(4)
    dropping = part(four, "when the maintainer drops an item", "when the maintainer merges or splits")

    has_all(dropping, "not at its `origin`", "`lineage_content`", "`existing`", "moves to `discarded`",
            "the items the rebuild created", "`lineage-item-missing`", "first appeared in this conversation")
    assert "an item new in this generation that the maintainer removes is simply deleted" not in four


def test_stage_5_drops_by_where_an_item_is_not_by_its_origin():
    five = stage(5)
    deleting = part(five, "a deleted item", "after each section is decided")

    has_all(deleting, "in the lineage", "existing nutrients", "whatever its `origin`", "moves to `discarded`",
            "first proposed in this conversation")
    assert "a deleted item that came from an earlier generation" not in five


def test_stage_4_never_copies_lineage_only_values():
    """T058: the lineage's `spec` is the old project's path and its `source` may be "rebuild"."""
    four = stage(4)
    kept = part(four, "a kept item of the lineage", "when `export_dir`")

    has_all(kept, "never copied", "old project's path", "`in_lineage` entry in `specs`", "`spec_dir`",
            '`"rebuild"`', "does not accept", "`maintainer`", ".sdd-rebuild/lineage.json", "`spec` is `null`")


def test_stage_6_does_not_ask_again_about_a_deleted_item_of_the_lineage():
    six = stage(6)
    missing = part(six, "`lineage-item-missing`", "`origin-changed`")

    has_all(missing, "already deleted", "`discarded`", "without asking again")
    has_any(six, "has not made yet")


def test_stage_4_new_ids_avoid_every_derived_from():
    """T057: an id that was merged or split away still stands for that item, so it is never taken again."""
    four = stage(4)
    new_ids = part(four, "every new item gets a new `id` that is never reused", "new items have `origin`")

    has_all(new_ids, "lineage", "existing nutrients", "discarded items included", "`derived_from`")
    merging = part(four, "when the maintainer merges or splits", "outcomes:")
    has_all(merging, "never reused", "cannot come back under its old `id`", "new `id`", "`derived_from`")


def test_stage_6_id_reused_takes_a_new_id_without_asking():
    six = stage(6)
    reused = part(six, "`id-reused` (", "fix each as")

    has_all(reused, "`derived_from`", "new `id` without asking")


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


# ------------------------------------------- coverage of contracts/skill.md


def contract_entries() -> set:
    """("item", N) for every numbered instruction and ("row", stage, n) for every result row of contracts/skill.md."""
    lines = text(CONTRACT_MD).split("\n")
    start = lines.index("## SKILL.md 的內文")
    end = lines.index("## README.md")
    entries: set = set()
    current_stage = None
    row = 0
    for line in lines[start:end]:
        heading = re.match(r"^### 階段 (\d+)", line)
        if heading:
            current_stage, row = int(heading.group(1)), 0
            continue
        item = re.match(r"^(\d+)\. ", line)
        if item:
            entries.add(("item", int(item.group(1))))
        if current_stage and line.startswith("| ") and not line.startswith("| 結果") and not line.startswith("|---"):
            row += 1
            entries.add(("row", current_stage, row))
    return entries


# Each entry: (section, needles). A needle is a string that must appear, or a tuple of which one must appear.
# They check that the meaning is there, not the wording.
COVERAGE = {
    ("item", 1): (RULES, ["read-only", "grep", "glob", "git --no-pager log", ("build",), "test", "stdin",
                          ("temporary file",)]),
    ("item", 2): (RULES, [".sdd-export/", ("only thing that writes", "exactly one write")]),
    ("item", 3): (RULES, ["speckit-", "/sdd-init"]),
    ("item", 4): (RULES, ["secret_files", "secret_hits", ("never quote", "never repeat")]),
    ("item", 5): (RULES, ["askuserquestion", "recommend", "multiselect", "each doubt gets its own question",
                          "plain text"]),
    ("item", 6): (RULES, ["traditional chinese", "translate"]),
    ("item", 7): (RULES, ["nothing is saved", "starts over"]),
    ("item", 8): (RULES, ["changes an earlier decision", "do not reopen"]),
    ("item", 9): (RULES, ["git add", "git commit", "git push"]),
    ("item", 10): (RULES, ["pending", "never make up"]),
    ("item", 11): (STAGES[1], [CHECK.lower(), "before you read any project file"]),
    ("item", 12): (STAGES[2], ["paths after `/sdd-export`", "--scope"]),
    ("item", 13): (STAGES[2], ["too_large", "areas", "multiselect", "do not read or open any project file yet"]),
    ("item", 14): (STAGES[2], ["partial", "included", "kept as they are"]),
    ("item", 15): (STAGES[3], ["read only the files in the `files` list", "constitution", "specs"]),
    ("item", 16): (STAGES[3], ["mixed", "own `source`"]),
    ("item", 17): (STAGES[3], ["actually does now", "evidence", "pending"]),
    ("item", 18): (STAGES[3], ["not how it is implemented"]),
    ("item", 19): (STAGES[3], ["decision", "pitfall", "reversed", "commit:<hash>", "is `pending`"]),
    ("item", 20): (STAGES[3], ["suspected bug", "both sides", "do not pick one"]),
    ("item", 21): (STAGES[3], ["never contain plans, tasks or code", "only as evidence for lessons"]),
    ("item", 22): (STAGES[4], ["do not compute the generation yourself"]),
    ("item", 23): (STAGES[4], ["in_lineage", "lineage_missing_specs", "still apply", "exactly as it is, unchanged",
                               "never copied into the draft", '`"rebuild"`']),
    ("item", 24): (STAGES[4], ["export_dir", "starting point", "one by one", "outside the chosen scope"]),
    ("item", 25): (STAGES[4], ["never reused", "discarded items included", "appears in a `derived_from`",
                               "split-out item gets a new `id`"]),
    ("item", 26): (STAGES[5], ["generation", "principles", "features", "doubts", "lessons", "pending"]),
    ("item", 27): (STAGES[5], ["accept it all", "moves to `discarded`", "whatever its `origin`"]),
    ("item", 28): (STAGES[5], ["one question per doubt", "`doubt`"]),
    ("item", 29): (STAGES[5], ["found none", "`maintainer` as evidence", "never invent"]),
    ("item", 30): (STAGES[5], ["short list"]),
    ("item", 31): (STAGES[5], ["nothing is written in this stage"]),
    ("item", 32): (STAGES[6], [VALIDATE.lower(), "before the final confirmation"]),
    ("item", 33): (STAGES[7], ["counts", "diff.base", "no differences"]),
    ("item", 34): (STAGES[7], ['`view`', "overwrite their changes", "merge"]),
    ("item", 35): (STAGES[7], ["confirm and write (recommended)", "change something", "stop"]),
    ("item", 36): (STAGES[8], [WRITE.lower()]),
    ("item", 37): (STAGES[9], [".sdd-export/nutrients.json", ".sdd-export/readme.md", "/sdd-rebuild", "commit"]),
    ("item", 38): (STAGES[9], ["`partial`", "running `/sdd-export` again"]),
    ("item", 39): (STAGES[9], ["changes their mind after the write", "edit or delete"]),
    # stage 1 results
    ("row", 1, 1): (STAGES[1], ["`uv` is not installed"]),
    ("row", 1, 2): (STAGES[1], ["`conflict`", "conflicts", "move or rename"]),
    ("row", 1, 3): (STAGES[1], ["`nutrients-unreadable`", "`nutrients-invalid`", "never overwrite it"]),
    ("row", 1, 4): (STAGES[1], ["`nutrients-newer`", "`lineage-newer`", "update this skill"]),
    ("row", 1, 5): (STAGES[1], ["`lineage-unreadable`", "`lineage-invalid`", "`lineage-conflict`",
                                "never treat the project as a first generation"]),
    ("row", 1, 6): (STAGES[1], ["`writable` is `false`", "continue (recommended)"]),
    ("row", 1, 7): (STAGES[1], ["`existing_generation` is not `null`", "stop and check first (recommended)"]),
    ("row", 1, 8): (STAGES[1], ['`nutrients` is `"edited"` or `"unknown"`', "maintainer's decisions"]),
    ("row", 1, 9): (STAGES[1], ["`inventory.files` is 0", "inventory.skipped"]),
    ("row", 1, 10): (STAGES[1], ["in every case that continues", "go to stage 2"]),
    # stage 2 results
    ("row", 2, 1): (STAGES[2], ["`too_large` is `false`: go to stage 3"]),
    ("row", 2, 2): (STAGES[2], ['`reason` is `"usage"`', "ask again which scope"]),
    ("row", 2, 3): (STAGES[2], ["still too large"]),
    ("row", 2, 4): (STAGES[2], ["refuses to narrow", "batches", "nothing was written and stop"]),
    ("row", 2, 5): (STAGES[2], ["chooses to stop: rule 7"]),
    # stage 3 results
    ("row", 3, 1): (STAGES[3], ["at least one feature with evidence: go to stage 4"]),
    ("row", 3, 2): (STAGES[3], ["not enough to propose any requirement", "nothing was written, and stop"]),
    ("row", 3, 3): (STAGES[3], ["cannot be read", "do not try another way"]),
    ("row", 3, 4): (STAGES[3], ["context is running out", "go back to stage 2"]),
    # stage 4 results
    ("row", 4, 1): (STAGES[4], ["the draft is built: go to stage 5"]),
    ("row", 4, 2): (STAGES[4], ["cannot be matched", "keep or discard"]),
    # stage 5 results
    ("row", 5, 1): (STAGES[5], ["accepts, changes or deletes items: update the draft"]),
    ("row", 5, 2): (STAGES[5], ["adds a requirement", "`maintainer` as evidence"]),
    ("row", 5, 3): (STAGES[5], ["already decided: rule 8"]),
    ("row", 5, 4): (STAGES[5], ["every section has been decided: go to stage 6"]),
    ("row", 5, 5): (STAGES[5], ["asks to stop: rule 7"]),
    # stage 6 results
    ("row", 6, 1): (STAGES[6], ["`ok` is `true`", "go to stage 7"]),
    ("row", 6, 2): (STAGES[6], ['`reason` is `"secret"`', "without repeating the value"]),
    ("row", 6, 3): (STAGES[6], ["format errors", "need no question"]),
    ("row", 6, 4): (STAGES[6], ["`unsupported` or `evidence`", "became pending"]),
    ("row", 6, 5): (STAGES[6], ["generation rules", "`lineage-item-missing`", "one question per item"]),
    ("row", 6, 6): (STAGES[6], ["exit code 3", "same outcome of stage 1"]),
    # stage 7 results
    ("row", 7, 1): (STAGES[7], ["confirm: go to stage 8"]),
    ("row", 7, 2): (STAGES[7], ["go back to the section of stage 5", "through stage 6 and this stage again"]),
    ("row", 7, 3): (STAGES[7], ["stop: rule 7"]),
    # stage 8 results
    ("row", 8, 1): (STAGES[8], ["exit code 0: go to stage 9"]),
    ("row", 8, 2): (STAGES[8], ['`reason` is `"changed"`', "go back to stage 7"]),
    ("row", 8, 3): (STAGES[8], ['`reason` is `"conflict"`', "whole confirmed draft", "do not write it anywhere else"]),
    ("row", 8, 4): (STAGES[8], ["any other exit code 3", "same outcome of stage 1"]),
    ("row", 8, 5): (STAGES[8], ['`reason` is `"os-error"`', "no half-written file", "stop (recommended)"]),
    ("row", 8, 6): (STAGES[8], ["asks to retry", "same confirmed draft", 'handle it as `"changed"`']),
    ("row", 8, 7): (STAGES[8], ['`"invalid"` or `"secret"`', "go back to stage 6"]),
}


def test_coverage_table_matches_the_contract():
    expected = contract_entries()

    assert {("item", n) for n in range(1, 40)} <= expected
    assert set(COVERAGE) == expected, (sorted(expected - set(COVERAGE)), sorted(set(COVERAGE) - expected))


@pytest.mark.parametrize("entry", sorted(COVERAGE, key=str), ids=lambda e: "-".join(map(str, e)))
def test_every_contract_entry_is_in_skill_md(entry):
    name, needles = COVERAGE[entry]
    haystack = section(name)
    for needle in needles:
        if isinstance(needle, tuple):
            has_any(haystack, *needle)
        else:
            assert needle.lower() in haystack, (entry, needle)


def cli_vocabulary() -> str:
    return text(CLI_MD) + "\n" + text(DATA_MODEL_MD)


# Backticked words in SKILL.md that are not fields or values of the script: tools, commands and placeholders.
NOT_FIELDS = {
    "uv", "git", "true", "false", "null", "check", "files", "validate", "write", "--scope", "--expect",
    "git --no-pager log", "git --no-pager ls-files", "git --no-pager blame", "nutrients.json",
}


def test_every_field_and_value_skill_md_names_exists_in_the_contracts():
    """Every backticked field or value (e.g. `inventory.too_large`, `"edited"`) is defined in cli.md or data-model.md."""
    vocabulary = cli_vocabulary()
    unknown = []
    for word in sorted(set(re.findall(r"`([^`\n]+)`", body()))):
        candidate = re.sub(r"\[\d+\]", "", word.strip('"'))
        if candidate in NOT_FIELDS or " " in candidate or "/" in candidate \
                or candidate.startswith(("speckit-", "[", "{", "<", "-", "commit:")):
            continue  # commands, git options, file paths, placeholders and examples, not fields of the script
        for part_name in candidate.split("."):
            if f"`{part_name}`" not in vocabulary and f'"{part_name}"' not in vocabulary:
                unknown.append(word)
                break
    assert unknown == [], unknown


def test_every_reason_and_check_name_is_handled():
    content = flat_body()
    reasons = ["usage", "invalid", "secret", "changed", "os-error", "conflict", "nutrients-unreadable",
               "nutrients-invalid", "nutrients-newer", "lineage-unreadable", "lineage-invalid", "lineage-newer",
               "lineage-conflict"]
    checks = ["json", "field", "id", "range", "code-block", "secret", "evidence", "unsupported", "spec", "dependency",
              "scope", "generation", "lineage-item-missing", "origin-changed", "origin-unknown", "revision-unmarked",
              "discard-lost", "discarded-active", "derived-unknown", "id-reused"]
    cli = text(CLI_MD)
    for value in reasons:
        assert f"`{value}`" in cli or f'"{value}"' in cli, value
        assert f"`{value}`" in content or f'`"{value}"`' in content, value
    for value in checks:
        assert f"`{value}`" in text(DATA_MODEL_MD), value
        assert f"`{value}`" in content, value


# ------------------------------------------------------- folder and README


def test_folder_holds_exactly_three_files():
    files = sorted(
        p.relative_to(SKILL_DIR).as_posix()
        for p in SKILL_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )

    assert files == ["README.md", "SKILL.md", "scripts/sdd_export.py"]


def test_files_use_lf_line_endings():
    for path in (SKILL_MD, README_MD, SCRIPT):
        data = path.read_bytes()
        assert b"\r" not in data, path.name
        assert data.endswith(b"\n"), path.name


def test_readme_is_traditional_chinese_without_paths_or_emails():
    readme = text(README_MD)

    assert len(CJK.findall(readme)) > 300
    assert not ABSOLUTE_PATH.search(readme)
    assert not EMAIL.search(readme)


def test_readme_usage_and_prerequisites():
    readme = text(README_MD)

    for needle in ("/sdd-export", "Spec Kit", "uv", "git", "disable-model-invocation", ".gitignore", "commit"):
        assert needle in readme, needle
    assert "非必要" in readme or "不是必要" in readme
    assert "維護者" in readme and ("啟動" in readme or "輸入" in readme)
    assert "舊專案" in readme


def test_readme_flow():
    readme = text(README_MD)

    flow = readme[readme.index("## 流程"):]
    order = [flow.index(word) for word in ("只讀", "**草稿", "**逐項", "**確認", "**寫入")]
    assert order == sorted(order), order
    assert "中途" in readme and "不會留下" in readme


def test_readme_output_and_generations():
    readme = text(README_MD)

    for needle in (".sdd-export/", "nutrients.json", "README.md", ".gitattributes", "唯一", "/sdd-rebuild", "新專案",
                   ".sdd-rebuild/lineage.json", "第一代", "世代", "origin"):
        assert needle in readme, needle


def test_readme_re_export_large_projects_and_secrets():
    readme = text(README_MD)

    for needle in ("再次匯出", "差異", "手動", "範圍", "分批", "機密", ".env", "無法涵蓋"):
        assert needle in readme, needle


def test_readme_what_it_never_does():
    readme = text(README_MD)
    never = readme[readme.index("## 不做的事"):]

    for needle in (".sdd-export/", "建置", "測試", "Spec Kit", "提交", "刪除"):
        assert needle in never, needle


# ------------------------------------------- found in the read-through (T053)


def test_unlisted_fields_need_no_action_only_unlisted_results_stop():
    intro = flat_body()[: flat_body().index("## " + RULES.lower())]

    has_any(intro, "exit code or a `reason` that no outcome mentions")
    has_any(intro, "need no action")
    has_all(intro, "`view`", "`gitattributes`")


def test_stage_1_outcomes_hold_when_later_stages_return_to_them():
    one = stage(1)

    has_any(one, "later stages send you here")
    assert "you have read nothing" not in one


def test_evidence_outside_the_current_scope_stays_valid():
    draft = section(DRAFT)

    has_any(draft, "outside the current scope are fine")
    assert "is in the `files` list" not in draft


def test_a_full_export_stays_full_when_a_scope_is_given():
    two = stage(2)

    has_any(two, "already `full`")
    has_any(two, "together with the areas already listed")


def test_stage_8_keeps_every_path_open():
    eight = stage(8)

    has_any(list_item(STAGES[8], '`reason` is `"changed"`'), "handle them as in stage 6")
    has_any(list_item(STAGES[8], '`reason` is `"os-error"`'), "may already hold the confirmed")
    has_any(list_item(STAGES[8], "wants to change the draft"), "go back to stage 5")
    assert "wants to change the draft" in eight


# ------------------- secrets that hand edits put into the existing nutrients, the lineage or the README


@pytest.mark.parametrize("reason, file", [("nutrients-invalid", ".sdd-export/nutrients.json"),
                                          ("lineage-invalid", ".sdd-rebuild/lineage.json")])
def test_stage_1_a_secret_in_the_existing_files_is_shown_by_path_only(reason, file):
    branch = stage_1_branch(reason)
    secret = part(branch, "`secret`")

    has_all(secret, file, "path", "remove")
    has_any(secret, "do not open", "never open")
    has_any(secret, "into the conversation")


def test_stage_1_re_export_after_a_secret_never_overwrites():
    branch = stage_1_branch("nutrients-invalid")

    has_all(branch, "never overwrite")
    # Both ways out are spelled out: fixed by hand, or deleted and exported afresh without the old content.
    has_any(branch, "after a fix")
    has_all(branch, "first export", "nothing of the old nutrients")


def sentences(content: str) -> list[str]:
    return re.split(r"(?<=[.:;])\s", content)


def test_skill_md_never_tells_you_to_read_the_nutrients_or_the_lineage():
    """A sentence that tells you to read or open one of them (the verb before the name) also says not to."""
    found = 0
    for sentence in sentences(flat_body()):
        if re.search(r"\b(read|open)\b.*(nutrients|lineage)\.json", sentence):
            found += 1
            assert re.search(r"\b(never|not|don't)\b", sentence) or "/sdd-rebuild" in sentence, sentence
    assert found, "the rule that forbids opening them is missing"


def test_rule_1_reads_the_readme_only_without_secret_lines():
    rules = section(RULES)
    exception = part(rules, "`.sdd-export/readme.md`", "never open")

    has_all(exception, "stage 7", "view_secret_lines", "empty")


def test_stage_7_does_not_open_a_readme_with_secret_lines():
    seven = stage(7)
    lines = part(seven, "it lists line numbers", "then ask one question")

    has_any(lines, "do not open the file", "never open the file")
    has_all(lines, "askuserquestion", "remove", "(recommended)", "check", "let the readme changes go", "stage 1")
    # Letting the changes go needs nothing from the file; write regenerates it with the state from check.
    has_all(lines, "regenerates", "--expect", "state")
    empty = part(seven, "it is empty", "it lists line numbers")
    has_all(empty, "merge", "read the file", "stage 6")
