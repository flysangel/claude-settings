"""Structure tests for home/CLAUDE.md.

The contract is specs/002-global-claude-md/contracts/claude-md-structure.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_MD = REPO_ROOT / "home" / "CLAUDE.md"
SKILLS_DIR = REPO_ROOT / "home" / "skills"

SECTIONS = ["溝通", "Git", "規格驅動開發"]
EXPECTATION_PREFIX = "  預期："


def read_bytes() -> bytes:
    return CLAUDE_MD.read_bytes()


def read_text() -> str:
    """Decode from bytes so that no newline translation hides a CR."""
    return read_bytes().decode("utf-8")


def parse_sections(text: str) -> list[tuple[str, list[str]]]:
    """Split the document into (second-level heading, body lines), in order."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def parse_rules(lines: list[str]) -> list[tuple[str, str | None]]:
    """Return (requirement, following non-empty line) for every top-level list item."""
    rules: list[tuple[str, str | None]] = []
    for index, line in enumerate(lines):
        if line.startswith("- "):
            following = next((l for l in lines[index + 1 :] if l.strip()), None)
            rules.append((line[2:], following))
    return rules


def section_rules(name: str) -> list[tuple[str, str | None]]:
    return parse_rules(dict(parse_sections(read_text()))[name])


# ------------------------------------------------------------ document level


def test_document_is_utf8_with_one_top_level_heading():
    lines = read_text().split("\n")

    assert [l for l in lines if l.startswith("# ")] == [lines[0]]


def test_exactly_three_sections_in_order():
    assert [name for name, _ in parse_sections(read_text())] == SECTIONS


def test_lf_line_endings_and_trailing_newline():
    data = read_bytes()

    assert b"\r" not in data
    assert data.endswith(b"\n")


# ------------------------------------------------- US1: 溝通與 Git 的規則


def test_every_rule_is_followed_by_exactly_one_expectation():
    lines = read_text().split("\n")
    rules = parse_rules(lines)

    assert rules
    for requirement, following in rules:
        assert following is not None and following.startswith(EXPECTATION_PREFIX), requirement
        assert following[len(EXPECTATION_PREFIX) :].strip(), requirement
    assert sum("預期：" in l for l in lines) == len(rules)


@pytest.mark.parametrize("name", ["溝通", "Git"])
def test_communication_and_git_sections_have_three_rules(name):
    assert len(section_rules(name)) == 3


def test_no_personal_information():
    text = read_text()

    assert not re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", text)
    assert "/home/" not in text
    assert "/Users/" not in text
    assert not re.search(r"\b[A-Za-z]:\\", text)


# --------------------------------------------- US2: 規格驅動開發引用的 skill

SDD_SKILLS = {"sdd-init", "sdd-update", "sdd-grill", "sdd-export", "sdd-rebuild", "sdd-drive"}


def referenced_sdd_skills() -> set[str]:
    return set(re.findall(r"sdd-[a-z0-9]+(?:-[a-z0-9]+)*", read_text()))


def test_referenced_sdd_skills_are_exactly_the_six_provided():
    referenced = referenced_sdd_skills()

    assert "sdd-derive" not in referenced
    assert referenced - SDD_SKILLS == set()
    assert SDD_SKILLS - referenced == set()


def test_sdd_section_has_a_preamble_and_five_rules():
    lines = dict(parse_sections(read_text()))["規格驅動開發"]
    first = next(l for l in lines if l.strip())

    assert not first.startswith("- ")
    assert len(parse_rules(lines)) == 5


def test_referenced_skills_exist_in_home_skills():
    referenced = sorted(referenced_sdd_skills())
    missing = [name for name in sorted(SDD_SKILLS) if not (SKILLS_DIR / name).is_dir()]
    if missing:
        pytest.skip("home/skills 尚未提供：" + "、".join(missing))

    for name in referenced:
        assert (SKILLS_DIR / name / "SKILL.md").is_file(), name
