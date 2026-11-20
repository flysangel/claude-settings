"""Structure tests for home/skills/sdd-init/.

The contract is specs/003-sdd-init/contracts/skill.md.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = REPO_ROOT / "home" / "skills" / "sdd-init"
SKILL_MD = SKILL_DIR / "SKILL.md"
README_MD = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "sdd_init.py"

CJK = re.compile(r"[⺀-鿿가-힯豈-﫿＀-￯]")
ABSOLUTE_PATH = re.compile(r"(?<![\w$}\"'.-])(/home/|/Users/|/root/|/tmp/|/usr/|/etc/|~/|[A-Za-z]:\\)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    lines = content.split("\n")
    assert lines[0] == "---"
    end = lines.index("---", 1)
    fields = {}
    for row in lines[1:end]:
        key, _, value = row.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields, "\n".join(lines[end + 1 :])


def inline_metadata(script: str) -> dict:
    lines = script.split("\n")
    assert lines[0] == "# /// script"
    end = lines.index("# ///", 1)
    return tomllib.loads("\n".join(row[2:] for row in lines[1:end]))


def test_folder_holds_exactly_three_files():
    files = sorted(
        p.relative_to(SKILL_DIR).as_posix()
        for p in SKILL_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )

    assert files == ["README.md", "SKILL.md", "scripts/sdd_init.py"]


def test_files_use_lf_line_endings():
    for path in (SKILL_MD, README_MD, SCRIPT):
        data = path.read_bytes()
        assert b"\r" not in data, path.name
        assert data.endswith(b"\n"), path.name


def test_skill_frontmatter():
    fields, _ = split_frontmatter(text(SKILL_MD))

    assert sorted(fields) == ["argument-hint", "description", "disable-model-invocation", "name"]
    assert fields["name"] == "sdd-init"
    assert fields["disable-model-invocation"] == "true"
    assert fields["argument-hint"] == "[remove]"
    description = fields["description"]
    assert description and not CJK.search(description)
    assert "Spec Kit" in description and "remove" in description.lower()


def test_skill_body_runs_the_script_and_names_both_next_steps():
    _, body = split_frontmatter(text(SKILL_MD))

    assert 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_init.py" init' in body
    assert 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_init.py" remove' in body
    for command in ("/sdd-grill", "/speckit-constitution", "/speckit-specify"):
        assert command in body


def test_skill_body_forbids_retrying_and_other_installs():
    _, body = split_frontmatter(text(SKILL_MD))
    lowered = body.lower()

    for phrase in ("exactly once", "exit code", "commit", "push", ".specify/", "speckit-*"):
        assert phrase in lowered
    assert "`uv` command does not" in body


def test_skill_is_english_without_absolute_paths_or_emails():
    content = text(SKILL_MD)

    assert not CJK.search(content)
    assert not ABSOLUTE_PATH.search(content)
    assert not EMAIL.search(content)


def test_readme_is_traditional_chinese_and_covers_the_contract():
    content = text(README_MD)

    assert len(CJK.findall(content)) > 100
    # Characters that differ between Traditional and Simplified Chinese.
    assert any(ch in content for ch in "檔錄導議")
    assert not any(ch in content for ch in "档录导议")
    for needle in (
        "/sdd-init",
        "/sdd-init remove",
        "`uv`",
        "`git`",
        "`bash`",
        "Git Bash",
        ".specify/sdd-init.json",
        ".specify/.gitattributes",
        "git add --chmod=+x",
        "網路",
    ):
        assert needle in content, needle
    assert not EMAIL.search(content)


def test_script_has_inline_metadata_without_dependencies():
    metadata = inline_metadata(text(SCRIPT))

    assert metadata["requires-python"] == ">=3.11"
    assert metadata["dependencies"] == []


def test_script_messages_are_english_and_carry_no_personal_data():
    content = text(SCRIPT)

    assert not CJK.search(content)
    assert not EMAIL.search(content)
    assert not ABSOLUTE_PATH.search(content)


def test_loading_the_script_as_a_module_does_nothing(sdd_init, tmp_path, monkeypatch, capsys):
    import importlib.util
    import sys

    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("sdd_init_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "sdd_init_probe", module)
    spec.loader.exec_module(module)

    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert list(tmp_path.iterdir()) == []
    assert callable(module.main)
