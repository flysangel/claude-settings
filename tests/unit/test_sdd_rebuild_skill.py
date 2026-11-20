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
