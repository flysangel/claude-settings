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


DELETE_CALLS = re.compile(r"\b(unlink|remove|rmtree|rmdir|removedirs|truncate)\(")


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
