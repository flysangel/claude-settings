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
