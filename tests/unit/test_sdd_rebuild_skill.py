"""Structure and content tests for home/skills/sdd-rebuild/.

The contract is specs/007-sdd-rebuild/contracts/skill.md. The checks look for the meaning of each required
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
SKILL_DIR = REPO_ROOT / "home" / "skills" / "sdd-rebuild"
SKILL_MD = SKILL_DIR / "SKILL.md"
README_MD = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "sdd_rebuild.py"
CLI_MD = REPO_ROOT / "specs" / "007-sdd-rebuild" / "contracts" / "cli.md"
EXPORT_SKILL_MD = REPO_ROOT / "home" / "skills" / "sdd-export" / "SKILL.md"
GRILL_SKILL_MD = REPO_ROOT / "home" / "skills" / "sdd-grill" / "SKILL.md"
EXPORT_DATA_MODEL = REPO_ROOT / "specs" / "006-sdd-export" / "data-model.md"

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


# ------------------------------------------------------- (T005) the script


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

    assert modules <= set(sys.stdlib_module_names) | {"__future__"}, modules - set(sys.stdlib_module_names)
    assert "importlib" in modules  # the neighbours are loaded at run time, not imported


def test_script_runs_no_command_itself():
    script = text(SCRIPT)

    # git runs only through sdd-grill's fingerprint; the script has no subprocess of its own
    assert "subprocess" not in script
    assert "os.system" not in script and "Popen" not in script


def test_script_is_english_without_paths_or_emails():
    script = text(SCRIPT)

    # The one piece of Traditional Chinese, the default discard reason, is lineage data (the lineage's text is
    # always Traditional Chinese), not a message; it is written with \u escapes, so the source has no CJK at all.
    assert not CJK.search(script)
    assert not ABSOLUTE_PATH.search(script)
    assert not EMAIL.search(script)
    assert script.count("DEFAULT_DISCARD_REASON = ") == 1
    constant = re.search(r'DEFAULT_DISCARD_REASON = "([^"]+)"', script).group(1)
    assert constant.encode("ascii").decode("unicode_escape") == "維護者決定捨棄"


DELETE_CALLS = re.compile(r"(?:\bos\.|\bshutil\.|\.)(unlink|remove|rmtree|rmdir|removedirs|truncate)\(")


def function_of_each_line(source: str) -> dict[int, str]:
    tree = ast.parse(source)
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for line in range(node.lineno, node.end_lineno + 1):
                owner[line] = node.name
    return owner


def test_script_deletes_only_in_clear():
    source = text(SCRIPT)
    owner = function_of_each_line(source)
    found = []
    for number, line in enumerate(source.split("\n"), start=1):
        code = line.split("#", 1)[0]
        for match in DELETE_CALLS.finditer(code):
            found.append((match.group(1), owner.get(number)))

    assert "rmtree" not in source and "removedirs" not in source
    assert found, "clear must remove the progress"
    for name, function in found:
        assert name in ("unlink", "rmdir"), name
        assert function == "remove_own_files", (name, function)


def test_script_writes_only_below_the_new_project():
    # Every write goes through write_file, whose target is joined to the new project's root by the caller;
    # nothing in the script builds a path from the old project and writes to it.
    source = text(SCRIPT)
    tree = ast.parse(source)
    writers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in ("write_bytes", "write_text", "open", "mkdir", "atomic_write", "replace", "rename"):
                writers.append(name)
    assert "write_bytes" not in writers and "write_text" not in writers and "open" not in writers
    for function in ("write_file", "ensure_own_folder"):
        body = ast.get_source_segment(source, next(n for n in ast.walk(tree)
                                                   if isinstance(n, ast.FunctionDef) and n.name == function))
        assert not re.search(r"\bold", body), function


# ------------------------------------------------------------- SKILL.md


def skill() -> str:
    return text(SKILL_MD)


def frontmatter() -> dict:
    content = skill()
    assert content.startswith("---\n")
    head = content.split("---\n", 2)[1]
    fields = {}
    for line in head.strip().split("\n"):
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def body() -> str:
    return skill().split("---\n", 2)[2]


HEADINGS = {
    "rules": "## Rules for the whole run",
    "progress": "## The progress",
    1: "## Stage 1: Start",
    2: "## Stage 2: Exporting the old project",
    3: "## Stage 3: Reading the nutrients",
    4: "## Stage 4: What the new project already has",
    5: "## Stage 5: Deciding item by item",
    6: "## Stage 6: New requirements",
    7: "## Stage 7: Adjustments from the lessons",
    8: "## Stage 8: Final summary and confirmation",
    9: "## Stage 9: The constitution",
    10: "## Stage 10: The specs",
    11: "## Stage 11: Verifying",
    12: "## Stage 12: The lineage",
    13: "## Stage 13: Finishing",
    "resume": "## Resuming",
}


def section(key) -> str:
    content = body()
    start = content.index(HEADINGS[key] + "\n")
    rest = content[start + len(HEADINGS[key]):]
    following = [rest.index("\n## ") for _ in [0] if "\n## " in rest]
    return HEADINGS[key] + (rest[: following[0]] if following else rest)


def blocks(part: str) -> list[str]:
    """Paragraphs and list items of a section, each as one string (continuation lines joined)."""
    result, current = [], []
    for line in part.split("\n"):
        starts = line.startswith(("- ", "* ")) or re.match(r"^\d+\. ", line) or not line.strip()
        if starts and current:
            result.append(" ".join(current))
            current = []
        if line.strip():
            current.append(line.strip())
    if current:
        result.append(" ".join(current))
    return result


def has_block(part: str, *words: str) -> bool:
    lowered = [block.lower() for block in blocks(part)]
    return any(all(word.lower() in block for word in words) for block in lowered)


def test_frontmatter():
    fields = frontmatter()

    assert list(fields) == ["name", "description", "argument-hint", "disable-model-invocation"]
    assert fields["name"] == "sdd-rebuild"
    assert fields["argument-hint"] == '"<old project path>"'
    assert fields["disable-model-invocation"] == "true"
    description = fields["description"].lower()
    for word in ("new project", "old project", "nutrients", "keep", "modify", "merge", "discard", "new requirements",
                 "spec kit", "lineage", "confirm"):
        assert word in description, word
    assert not CJK.search(fields["description"])


def test_skill_is_english_without_paths_or_emails():
    content = skill()

    assert not CJK.search(content)
    assert not ABSOLUTE_PATH.search(content)
    assert not EMAIL.search(content)


def test_sections_are_in_stage_order():
    content = body()
    positions = [content.index(HEADINGS[key] + "\n") for key in
                 ["rules", "progress", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, "resume"]]

    assert positions == sorted(positions)


def test_the_script_is_always_run_the_same_way():
    content = body()
    runs = re.findall(r'uv run "\$\{CLAUDE_SKILL_DIR\}/scripts/sdd_rebuild\.py" (\w+)', content)

    assert set(runs) == {"check", "save", "preview", "claim", "verify", "lineage", "focus", "clear"}
    assert "sdd_rebuild.py" not in re.sub(r'uv run "\$\{CLAUDE_SKILL_DIR\}/scripts/sdd_rebuild\.py"', "", content)


# ------------------------------------------------- (T021) general rules

GENERAL_RULES = {
    1: ("old project", "plan", "tasks", "read", "grep", "glob", "stage 2"),
    2: ("never write", "old project"),
    3: ("confirm", "speckit-", "claim", "lineage", "focus", "save"),
    4: ("speckit-constitution", "speckit-specify", "by hand", ".specify/feature.json", ".sdd-rebuild/"),
    5: ("derived_from", "origin", "revised", "spec_dir", "script"),
    6: ("askuserquestion", "recommend", "one decision", "plain text"),
    7: ("traditional chinese", "language"),
    8: ("secret", "what is needed"),
    9: ("save", "heredoc", "after every decision"),
    10: ("stop", "/sdd-rebuild", "nothing is generated"),
    11: ("push", "commit", ".git/"),
    12: ("exit code", "reason", "stop"),
}


@pytest.mark.parametrize("number", sorted(GENERAL_RULES))
def test_general_rules(number):
    rules = section("rules")
    block = next((b for b in blocks(rules) if b.startswith(f"{number}. ")), None)

    assert block is not None, f"rule {number} is missing"
    for word in GENERAL_RULES[number]:
        assert word in block.lower(), (number, word)


def test_rule_3_names_save_as_the_only_write_before_confirming():
    assert has_block(section("rules"), "only write", "save", "before", "confirm")


# ---------------------------------------- outcomes of every stage (T070)
# contracts/skill.md "階段與結果的數量": 17 + 5 + 14 + 2 + 5 + 3 + 3 + 6 + 3 + 6 + 7 + 7 + 4 + 12 = 94.
# Each outcome names the words a block (a paragraph or list item) of its stage must hold together.

OUTCOMES = {
    1: [
        ("present", "resuming"),
        ("ours", "stage 3"),
        ("`none`", "`empty`", "stage 2"),
        ('"conflict"', ".specify/sdd-rebuild/", "stop", "nothing"),
        ("progress-unreadable", "clear", "check"),
        ("old-mismatch", "old_project", "old.path"),
        ("dependency", "missing", "deploy", "stop", "nothing"),
        ("speckit-missing", "/sdd-init", "stop", "nothing"),
        ("speckit-incomplete", "missing", "/sdd-update", "stop", "nothing"),
        ("old-required", "path"),
        ("old-missing", "old-not-folder", "stop", "nothing"),
        ("same-project", "old-inside-new", "new-inside-old", "stop", "nothing"),
        ("rebuilt", "/sdd-grill", "/sdd-export", "stop", "nothing"),
        ("rebuild-conflict", "rebuild_conflicts", "stop", "nothing"),
        ("nutrients-conflict", "conflicts", "stop", "nothing"),
        ("nutrients-unreadable", "nutrients-invalid", "nutrients_errors", "stop", "nothing"),
        ("nutrients-newer", "update", "stop", "nothing"),
    ],
    2: [
        ("chooses to stop", "either project"),
        ("/sdd-export", "/sdd-rebuild", "old project", "stop"),
        ("sdd-export", "stops", "new project"),
        ("write", "check --old", "ours", "stage 3", "stage 1"),
        ("interrupted", "stage 1"),
    ],
    3: [
        ('"present"', '"used"', "stage 4"),
        ('"not-needed"', "stage 4"),
        ("needs_old_lineage", "git history", "skipped"),
        ('"mismatch"', "same project"),
        ("old_lineage_errors", "unreadable", "invalid"),
        ('"newer"', "update"),
        ('"conflict"', "not written by sdd-rebuild"),
        ("chooses to stop", "/sdd-rebuild", "nothing"),
        ("skipped", "final summary", "final report", "stage 4"),
        ("partial", "/sdd-export", "stage 2"),
        ("save", "succeeds", "stage 4"),
        ("`source`", "check", "stage 1"),
        ("`conflict`", "stage 1"),
        ("os-error", "without saving", "stop"),
    ],
    4: [
        ("decided", "save", "stage 5"),
        ("existing spec", "/sdd-grill", "never"),
    ],
    5: [
        ("every item", "stage 6"),
        ("changes an earlier decision", "save"),
        ("contradict", "both sides"),
        ("stop", "rule 10"),
        ("`invalid`", "`secret`", "save"),
    ],
    6: [
        ("no new requirement", "stage 7"),
        ("overlap", "existing feature"),
        ("stop", "rule 10"),
    ],
    7: [
        ('"lessons"', "stage 8"),
        ("contradict", "both sides"),
        ("no adjustment", "stage 8"),
    ],
    8: [
        ("`ok` is `false`", "unaccounted", "id-taken", "pending-undecided"),
        ("next-export", "lineage-format", "stop", "defect"),
        ("confirms", '"confirmed"', "stage 9"),
        ("`invalid`", "preview", "again"),
        ("change", "stage 5", "preview"),
        ("stop", "rule 10"),
    ],
    9: [
        ("comparison", "stage 10"),
        ("speckit-constitution", "fails", "stop", "/sdd-rebuild"),
        ("still missing", "by hand", "stop"),
    ],
    10: [
        ("claim", "succeeds", "stage 11"),
        ("`none`", "incomplete", "again"),
        ("`ambiguous`", "`mismatch`", "--dir", "candidates"),
        ("not-next", "check", "next"),
        ("interrupted", "claim", "specify"),
        ("number", "order", "stage 11"),
    ],
    11: [
        ("`ok`", "stage 12"),
        ("existing-spec-changed", "constitution-changed", "restore", "start over", "stop"),
        ("spec-missing", "restore", "never generate", "stop"),
        ("spec-not-new", "dependency-order", "stop"),
        ("existing-spec-missing", "restore", "stop"),
        ("not-reviewed", "next"),
        ("unexpected", "final report", "never delete"),
    ],
    12: [
        ("unchanged", "stage 13"),
        ("mismatch-documents", "stage 11"),
        ("lineage-changed", "overwrite", "stop"),
        ("rebuild-conflict", "stop"),
        ("`invalid`", "by hand", "stop"),
        ("internal", "defect", "stop"),
        ("os-error", "/sdd-rebuild", "stop"),
    ],
    13: [
        ("focus", "succeeds", "clear"),
        ("mismatch-documents", "restore", "start over"),
        ("not-regular", ".specify/feature.json"),
        ("clear", "`conflict`", "report"),
    ],
    "resume": [
        ("`decide`", "continue", "start over"),
        ("`constitution`", "back to the discussion", "stage 9"),
        ("`review-constitution`", "comparison", "speckit-constitution"),
        ("`claim`", "next.feature", "not generate"),
        ("`specify`", "stage 10"),
        ("`review`", "comparison"),
        ("`verify`", "stage 11"),
        ("`focus`", "`clear`", "stage 13", "start over"),
        ("unavailable", "snapshot"),
        ("source_diff", "--refresh-source", "snapshot", "start over"),
        ("start over", "kept", "existing", "clear"),
        ("change a decision", "finish", "/sdd-grill"),
    ],
}


def test_there_are_94_outcomes():
    counts = {key: len(value) for key, value in OUTCOMES.items()}

    assert counts == {1: 17, 2: 5, 3: 14, 4: 2, 5: 5, 6: 3, 7: 3, 8: 6, 9: 3, 10: 6, 11: 7, 12: 7, 13: 4, "resume": 12}
    assert sum(counts.values()) == 94


@pytest.mark.parametrize("stage, words", [(stage, words) for stage, entries in OUTCOMES.items() for words in entries],
                         ids=lambda value: str(value))
def test_every_outcome_has_a_next_step(stage, words):
    assert has_block(section(stage), *words), (stage, words)


# ------------------------------------------------- (T021-T024) instructions


def test_stage_1_asks_for_a_path_and_never_searches():
    part = section(1)

    assert has_block(part, "do not search")
    assert has_block(part, "check", "before")


def test_check_comes_before_anything_else():
    content = body()
    first_run = content.index('scripts/sdd_rebuild.py" check')

    assert first_run < content.index('scripts/sdd_rebuild.py" save')
    assert first_run < content.index("../sdd-export/SKILL.md")


def test_stage_3_reads_only_the_check_output():
    part = section(3)

    assert has_block(part, "nutrients", "check", "never read")
    assert has_block(part, "nutrients_edited")
    assert has_block(part, "coverage", "partial", "included")
    assert "old_lineage" in part and '"skipped"' in part and '"used"' in part and '"not-needed"' in part
    summary = part.index("pending")
    assert summary < part.index('"stage": "items"')
    assert has_block(part, '"phase": "deciding"', '"stage": "items"')


def test_stage_4_compares_with_what_exists():
    part = section(4)

    assert has_block(part, "written", "keep", "amend")
    assert has_block(part, "create", "missing", "template")
    assert has_block(part, "existing_spec", "never")
    assert has_block(part, "existing spec", "first")


def test_stage_8_summary_and_order():
    part = section(8)

    assert part.index('"stage": "summary"') < part.index('sdd_rebuild.py" preview')
    assert part.index('sdd_rebuild.py" preview') < part.index('"phase": "confirmed"')
    for word in ("kept", "modified", "merged", "split", "discarded", "added", "pending_decided", "adjustments",
                 "order", "action", "skipped"):
        assert word in part, word
    assert has_block(part, "confirm", "change", "stop", "recommended")


def test_stage_9_constitution():
    part = section(9)

    assert has_block(part, "speckit-constitution", "only", "confirmed")
    assert has_block(part, "both directions")
    assert has_block(part, '"written"') and has_block(part, '"reviewed"')
    assert has_block(part, "governance", "after the confirmation")
    assert has_block(part, "keep", "not-needed")


def test_stage_10_specs():
    part = section(10)

    assert has_block(part, "speckit-specify", "one", "time")
    assert has_block(part, "number")
    assert has_block(part, "assumptions")
    assert part.index('sdd_rebuild.py" claim') < part.index("go to the next feature")
    assert has_block(part, '"reviewed": true')
    assert has_block(part, "clarif", "deferred", "for_plan")


def test_stage_11_verify_comes_before_the_lineage():
    content = body()

    assert content.index('sdd_rebuild.py" verify') < content.index('sdd_rebuild.py" lineage')
    assert has_block(section(11), "spec-missing", "never generate")


def test_stage_12_lineage():
    assert ".sdd-rebuild/lineage.json" in section(12)


def test_stage_13_finishing_order_and_report():
    part = section(13)

    assert part.index('sdd_rebuild.py" focus') < part.index('sdd_rebuild.py" clear')
    report = part[part.index('sdd_rebuild.py" clear'):]
    for word in ("order", "depend", "existing spec", ".specify/feature.json", "generation", ".sdd-rebuild/lineage.json",
                 "commit", "skipped", "unexpected", "/sdd-drive", "after the confirmation", "new in this generation"):
        assert word.lower() in report.lower(), word
    assert has_block(part, "/sdd-drive", "stop", "plan", "tasks")
    assert has_block(part, "no spec", "/sdd-drive")


def test_resume_shows_where_the_run_stands():
    part = section("resume")

    assert has_block(part, "phase", "stage", "decided", "next")
    assert has_block(part, "changed", "deciding", "stage 4")
    assert has_block(part, "changed", "confirmed", "verify")
    assert has_block(part, "lineage", "written", "not", "start over")


# -------------------------------------------------- (T044) stages 5 to 7


def test_stage_5_instructions():
    part = section(5)

    assert has_block(part, "keep everything", "item by item")
    assert "merge" in part and "split" in part and "discard" in part
    assert has_block(part, "principles", "features", "lessons", "order")
    assert has_block(part, '"derived"', "from")
    assert has_block(part, "split", "keeps", '"inherit"')
    assert has_block(part, "id-taken", "new id")
    assert has_block(part, "pending", "one", "pending_decided", "never")
    assert has_block(part, '"stage": "items"')


def test_stage_6_instructions():
    part = section(6)

    assert "../sdd-grill/SKILL.md" in part and "Rules for questioning" in part
    assert has_block(part, "not", "progress", "commands")
    assert has_block(part, '"new"', "depend")
    assert "for_plan" in part and "deferred" in part
    assert has_block(part, '"stage": "new"')


def test_stage_7_instructions():
    part = section(7)

    assert has_block(part, "adjustments", "lesson", "one")
    assert has_block(part, "never", "principle", "requirement", "agree")
    assert has_block(part, "lesson", "still", "discards")


def test_stages_5_to_8_come_in_order():
    content = body()

    assert content.index(HEADINGS[5]) < content.index(HEADINGS[6]) < content.index(HEADINGS[7]) < content.index(HEADINGS[8])


def test_the_rules_for_questioning_of_sdd_grill_still_exist():
    assert "\n## Rules for questioning\n" in text(GRILL_SKILL_MD)


# ---------------------------------------------------------- (T065) stage 2

EXPORT_GIT_FORMS = (
    "git --no-pager log --oneline -n <n> [-- <path>]",
    "git --no-pager log --stat -n <n> [<commit>] [-- <path>]",
    "git --no-pager ls-files",
    "git --no-pager blame -- <path>",
)


def test_stage_2_instructions():
    part = section(2)

    assert has_block(part, ".sdd-export/", "only", "confirm")
    assert has_block(part, "export now", "recommended", "/sdd-export", "stop")
    assert has_block(part, "export_skill", "false", "deploy", "stop")
    assert "${CLAUDE_SKILL_DIR}/../sdd-export/SKILL.md" in part
    assert "Rules for the whole run" in part and "Stage 1" in part and "Stage 9" in part
    assert "${CLAUDE_SKILL_DIR}/../sdd-export/scripts/sdd_export.py" in part
    assert '--project "<old.path>"' in part
    assert has_block(part, "read", "grep", "one", "<old.path>/")
    assert has_block(part, "glob", "stage 2", "folder names")
    assert has_block(part, "four", "-C \"<old.path>\"", "nothing else")
    assert has_block(part, "nothing", "new project", "save")
    assert has_block(part, "stage 9", "check --old", "/sdd-rebuild")


def test_stage_2_copies_no_rule_text_of_sdd_export():
    part = section(2)

    for form in EXPORT_GIT_FORMS:
        assert form not in part
    assert "secret_files" in part  # named, so the reader keeps the protection; the rule itself is sdd-export's


def test_the_parts_of_sdd_export_that_stage_2_refers_to_still_exist():
    export = text(EXPORT_SKILL_MD)

    assert "\n## Rules for the whole run\n" in export
    for number in range(1, 10):
        assert f"\n## Stage {number}:" in export
    assert "\n## Stage 9: Final report\n" in export
    for form in EXPORT_GIT_FORMS:
        assert form in export


def test_stage_2_comes_before_stage_3():
    content = body()

    assert content.index(HEADINGS[2]) < content.index(HEADINGS[3])


# ------------------------------------------------------- (T070) global order


def test_confirmation_comes_before_any_generation():
    content = body()
    content = content[content.index(HEADINGS["progress"]):]
    confirmed = content.index('"phase": "confirmed"')

    for later in ('Skill tool to invoke `speckit-constitution`', 'sdd_rebuild.py" claim', 'sdd_rebuild.py" lineage',
                  'sdd_rebuild.py" focus'):
        assert confirmed < content.index(later), later
    assert content.index(HEADINGS[9]) < content.index(HEADINGS[10])
    assert content.index('sdd_rebuild.py" lineage') < content.index('sdd_rebuild.py" focus')


NAMES = re.compile(r"`([a-z][a-z0-9_.-]*[a-z0-9])`")
OTHER_NAMES = {
    # names of sdd-export, sdd-grill and Spec Kit that the skill refers to
    "files", "secret_files", "secret_hits", "write", "speckit-constitution", "speckit-specify", "sdd-export",
    "sdd-grill", "sdd-rebuild", "tools/deploy.py", "home", "zh-tw", "spec.md", "saved", "uv",
}


def test_every_name_the_skill_uses_is_defined():
    known = text(CLI_MD) + text(REPO_ROOT / "specs" / "007-sdd-rebuild" / "data-model.md") + text(EXPORT_DATA_MODEL)

    def defined(name: str) -> bool:
        if name in OTHER_NAMES or name.startswith((".", "specs/")):
            return True
        # a dotted name (next.feature, saved.old_project) is defined when each of its parts is
        return all(f"`{part}`" in known or f'"{part}"' in known for part in name.split("."))

    unknown = sorted({name for name in NAMES.findall(body()) if not defined(name)})

    assert unknown == []


REASONS = ("usage", "old-mismatch", "invalid", "secret", "frozen", "finished", "source", "no-progress", "none",
           "ambiguous", "mismatch", "not-next", "mismatch-documents", "lineage-changed", "internal", "not-regular",
           "conflict", "os-error", "dependency", "speckit-missing", "speckit-incomplete", "old-required", "old-missing",
           "old-not-folder", "same-project", "old-inside-new", "new-inside-old", "rebuilt", "rebuild-conflict",
           "nutrients-conflict", "nutrients-unreadable", "nutrients-invalid", "nutrients-newer", "progress-unreadable")


def test_every_reason_is_in_the_cli_contract_and_most_are_handled():
    cli = text(CLI_MD)
    content = body()

    for reason in REASONS:
        assert f"`{reason}`" in cli, reason
    handled = [reason for reason in REASONS if f"`{reason}`" in content]
    assert set(REASONS) - set(handled) <= {"usage"}, set(REASONS) - set(handled)


# ------------------------------------- (T060) the contract text of 006 data-model
# The expected text is copied from specs/007-sdd-rebuild/plan.md "對 006 文件的修改" (approved by the maintainer);
# plan.md is not read at run time.

ROWS_BEFORE = ['| 原樣保留 | 沿用 | 沿用 | 沿用 | 沿用 | |', '| 修改後保留 | 沿用 | 沿用 | 沿用並加上 `generation` | 沿用 | |', '| 合併多個項目 | 新取（見表後） | `generation` | 空 | 被合併的 `id` | 被合併的項目不必另記為捨棄 |', '| 拆分一個項目 | 新取（見表後） | `generation` | 空 | 被拆分的 `id` | |']
ROWS_AFTER = ['| 原樣保留 | 沿用 | 沿用 | 沿用 | 沿用並補入祖先（見表後） | |', '| 修改後保留 | 沿用 | 沿用 | 沿用並加上 `generation` | 沿用並補入祖先（見表後） | |', '| 合併多個項目 | 新取（見表後） | `generation` | 空 | 被合併的 `id`，並補入祖先（見表後） | 被合併的項目不必另記為捨棄 |', '| 拆分一個項目 | 新取（見表後） | `generation` | 空 | 被拆分的 `id`，並補入祖先（見表後） | 原項目可以同時依「原樣保留」或「修改後保留」保留 |']
ADDED_PARAGRAPHS = (
    '「補入祖先」：007 以來源養分的所有有效項目，以及舊專案的 `.sdd-rebuild/lineage.json`（存在、通過驗證且世代與養分相同時）的所有有效項目，\n建立「`id` → `derived_from`」的祖先表（同一個 `id` 兩邊都有時取聯集，養分的在前）。寫入的 `derived_from` 是：直接來源依序在前\n（保留與修改的項目是祖先表中它自己的清單，合併與拆分的項目是被合併或被拆分的 `id`），接著依直接來源的順序，把每個直接來源在祖先表中的\n`derived_from` 依記錄的順序深度優先展開；去重，保留第一次出現的位置。如此一來，經過合併再拆分的項目仍記得最早的來源，\n那些 `id` 留在世代紀錄中而被世代規則 9 擋下重用；世代規則 8 允許沿用世代紀錄已記下的來源，世代規則 5 只比較內容欄位，\n所以補入後變長的 `derived_from` 不影響下一次匯出。',
    '已知限制（維護者接受，2026-11-20）：捨棄紀錄沒有 `derived_from`，被捨棄項目的來源只保留到該次捨棄為止（被捨棄的項目本身仍在\n`discarded`，不能重用）；匯出時的合併或拆分只記下直接來源（世代規則 8 不允許在匯出時補入），下一次重建由舊專案的世代紀錄補上，\n但同一代內第二次匯出合併了第一次匯出才建立的項目時，第一次匯出記下的來源會遺失。',
)
UNCHANGED_ROWS = (
    "| 情況 | `id` | `origin` | `revised` | `derived_from` | 其他 |",
    "| 重建時新增 | 新取（見表後） | `generation` | 空 | 空 | `source` 為 `\"rebuild\"` |",
    "| 捨棄 | 沿用 | 沿用 | | | 移到 `discarded`，`discarded_in` 為 `generation` |",
    "| 來源養分的 `discarded` | 沿用 | 沿用 | | | 原樣帶入 |",
    "| 來源養分中 `pending` 的項目 | 依維護者的決定套用上面任一列 | | | | 不得以 `pending` 寫入 |",
    "### 007 寫入時 MUST 遵守的規則",
)


def test_006_data_model_holds_the_approved_rows():
    content = text(EXPORT_DATA_MODEL)

    for row in ROWS_AFTER:
        assert row + "\n" in content, row
    for row in ROWS_BEFORE:
        assert row + "\n" not in content, row
    for row in UNCHANGED_ROWS:
        assert row in content, row


def test_006_data_model_holds_the_two_approved_paragraphs_in_place():
    content = text(EXPORT_DATA_MODEL)
    rule_9 = content.index("兩個不同的項目（世代規則 9）。")
    every_item = content.index("來源養分中的每一個有效項目 MUST 對應到上表其中一列")

    for paragraph in ADDED_PARAGRAPHS:
        assert paragraph in content
        assert rule_9 < content.index(paragraph) < every_item
    assert content.index(ADDED_PARAGRAPHS[0]) < content.index(ADDED_PARAGRAPHS[1])


# ------------------------------------------------ (T068) the folder, README


def test_the_folder_holds_three_files():
    found = sorted(p.relative_to(SKILL_DIR).as_posix() for p in SKILL_DIR.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts)

    assert found == ["README.md", "SKILL.md", "scripts/sdd_rebuild.py"]


def readme() -> str:
    return text(README_MD)


def test_readme_is_traditional_chinese():
    assert len(CJK.findall(readme())) > 200
    assert not ABSOLUTE_PATH.search(readme()) and not EMAIL.search(readme())


@pytest.mark.parametrize("words", [
    ("/sdd-rebuild <舊專案路徑>", "/sdd-export", ".sdd-export/"),
    ("Spec Kit", "sdd-export", "sdd-grill", "uv"),
    ("逐項", "新需求", "教訓", "確認", "constitution", "spec", "世代紀錄", "/sdd-drive"),
    (".specify/sdd-rebuild/", "快照", "清除"),
    (".sdd-rebuild/lineage.json", "MUST", "提交", "derived_from", "祖先"),
    ("已知限制", "第二次匯出", "捨棄", "略過"),
    ("plan", "tasks", "程式碼", "不覆蓋", "push"),
])
def test_readme_covers(words):
    content = readme()

    for word in words:
        assert word in content, word


def test_readme_lists_the_three_known_limitations():
    content = readme()
    section_start = content.index("已知限制")
    limits = content[section_start:]

    assert "同一代" in limits and "第一次" in limits
    assert "被捨棄" in limits and "不能重用" in limits
    assert "舊專案的世代紀錄" in limits and "遺失" in limits


# --------------------------- (T070) items 13 to 50 of contracts/skill.md, by number
# Items 1 to 12 are GENERAL_RULES above; the outcome rows are OUTCOMES above.

ITEMS = {
    13: (1, ("old-required", "do not search")),
    14: (1, ("check", "before anything else")),
    15: (2, ("export now", "/sdd-export", "stop")),
    16: (2, ("export_skill", "false", "stop")),
    17: (2, ("../sdd-export/SKILL.md", "rules for the whole run")),
    18: (3, ("nutrients", "never read")),
    19: (3, ("partial", "included")),
    20: (3, ("old_lineage", "needs_old_lineage")),
    21: (3, ("first progress", '"phase": "deciding"')),
    22: (4, ("keep", "amend")),
    23: (4, ("existing_spec", "never change")),
    24: (4, ("neither", "skip")),
    25: (5, ("keep everything", "item by item")),
    26: (5, ("principles", "features", "lessons", "one item per question")),
    27: (5, ("pending", "pending_decided", "never record")),
    28: (5, ("after every decision", '"stage": "items"')),
    29: (6, ("rules for questioning", "../sdd-grill/SKILL.md")),
    30: (6, ("after every decision", '"stage": "new"')),
    31: (7, ("adjustments", "lesson", "own question")),
    32: (7, ("still applies", "discards")),
    33: (8, ('"stage": "summary"', "preview")),
    34: (8, ("summary", "completely")),
    35: (8, ("confirm and generate", "recommended")),
    36: (9, ("speckit-constitution", "only the confirmed principles")),
    37: (9, ("both directions",)),
    38: (10, ("speckit-specify", "assumptions")),
    39: (10, ("claim", "before invoking")),
    40: (10, ("compare", "summary", "clarifying")),
    41: (11, ("verify", "before the lineage")),
    42: (12, ("lineage",)),
    43: (13, ("focus", "clear")),
    44: (13, ("/sdd-drive",)),
    45: ("resume", ("phase", "stage", "next.step")),
    46: ("resume", ("source_changed", "source_diff")),
    47: ("resume", ("changed", "stage 4", "verify")),
    48: ("resume", ("next.step",)),
    49: ("resume", ("start over", "kept", "existing content")),
    50: ("resume", ("change a decision", "finish as confirmed")),
}


def test_items_13_to_50_are_all_listed():
    assert sorted(ITEMS) == list(range(13, 51))


@pytest.mark.parametrize("number", sorted(ITEMS))
def test_items_13_to_50(number):
    stage, words = ITEMS[number]
    part = section(stage).lower()

    for word in words:
        assert word.lower() in part, (number, word)


# ------------------------------------- (T072) checks added by the read-through


def test_walkthrough_fixes_stay():
    assert has_block(section("progress"), "existing-spec", "existing-spec-missing")
    assert has_block(section(3), "os-error", "confirmation", "summary", "stop")
    assert has_block(section(2), ".sdd-export/README.md", "stage 7")
    assert has_block(section(4), "neither", "stage 5")
    assert has_block(section(5), "keep everything", "not in", "discards")
    assert has_block(section(5), "discard it", "take it out of the target")
    assert has_block(section(11), "other than `not-reviewed`", "only")
    assert has_block(section("resume"), "`items`", "stage 4", "stage 5")
