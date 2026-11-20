"""Structure tests for home/skills/sdd-update/.

The contract is specs/004-sdd-update/contracts/skill.md.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = REPO_ROOT / "home" / "skills" / "sdd-update"
SKILL_MD = SKILL_DIR / "SKILL.md"
README_MD = SKILL_DIR / "README.md"
SCRIPT = SKILL_DIR / "scripts" / "sdd_update.py"
SDD_INIT_SCRIPT = REPO_ROOT / "home" / "skills" / "sdd-init" / "scripts" / "sdd_init.py"

CJK = re.compile(r"[⺀-鿿가-힯豈-﫿＀-￯]")
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

    assert files == ["README.md", "SKILL.md", "scripts/sdd_update.py"]


def test_files_use_lf_line_endings():
    for path in (SKILL_MD, README_MD, SCRIPT):
        data = path.read_bytes()
        assert b"\r" not in data, path.name
        assert data.endswith(b"\n"), path.name


def test_skill_frontmatter():
    fields, _ = split_frontmatter(text(SKILL_MD))

    assert sorted(fields) == ["description", "disable-model-invocation", "name"]
    assert fields["name"] == "sdd-update"
    assert fields["disable-model-invocation"] == "true"
    description = fields["description"]
    assert description and not CJK.search(description)
    assert "Spec Kit" in description and "latest stable" in description
    assert description.count(". ") == 0 and description.endswith(".")


def test_skill_body_runs_the_script_without_arguments():
    _, body = split_frontmatter(text(SKILL_MD))

    assert 'uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_update.py"' in body
    assert 'sdd_update.py" ' not in body  # nothing is appended to the command
    lowered = body.lower()
    assert "no arguments" in lowered and "downgrade" in lowered and "exactly once" in lowered


def test_skill_body_reports_everything():
    _, body = split_frontmatter(text(SKILL_MD))

    for word in ("`updated`", "`created`", "`removed`", "`kept`", "`staged`", "`warning`", "`Git:`", "`Next:`"):
        assert word in body, word
    assert ".specify/sdd-update/" in body


def test_skill_body_forbids_retrying_merging_and_committing():
    _, body = split_frontmatter(text(SKILL_MD))
    lowered = body.lower()

    assert "exit code" in lowered
    assert "Do NOT run the script again." in body
    assert "do NOT run `specify` yourself" in body
    assert "`uv` command does not" in body
    for phrase in (".specify/", "speckit-*", "/sdd-init"):
        assert phrase in body
    assert "Do NOT run it yourself." in body
    assert "Do NOT merge kept files" in body
    assert "do NOT modify or delete the comparison copies" in body
    assert "Do NOT commit" in body and "do NOT push" in body
    assert "MUST NOT" in body or "Do NOT" in body


def test_skill_is_english_without_absolute_paths_or_emails():
    content = text(SKILL_MD)

    assert not CJK.search(content)
    assert not ABSOLUTE_PATH.search(content)
    assert not EMAIL.search(content)


def test_readme_is_traditional_chinese_and_covers_the_contract():
    content = text(README_MD)

    assert len(CJK.findall(content)) > 100
    assert any(ch in content for ch in "檔錄導護")
    assert not any(ch in content for ch in "档录导护")
    for needle in (
        "/sdd-update",
        "`uv`",
        "`git`",
        "`bash`",
        "Git Bash",
        ".specify/memory/",
        "specs/",
        ".specify/sdd-update/",
        ".new",
        "/sdd-init",
        "sdd-init",
        "git add --chmod=+x",
        "網路",
        "降版",
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


def test_script_uses_only_the_standard_library():
    content = text(SCRIPT)
    imported = set(re.findall(r"^(?:from|import) (\w+)", content, re.MULTILINE))

    assert imported <= {"__future__", "importlib", "json", "os", "re", "shutil", "sys", "tempfile", "dataclasses", "pathlib"}


def test_script_does_not_copy_sdd_init():
    script = text(SCRIPT)
    shared = text(SDD_INIT_SCRIPT)

    # None of sdd-init's functions is defined again here.
    defined_there = set(re.findall(r"^def (\w+)", shared, re.MULTILINE))
    defined_here = set(re.findall(r"^def (\w+)", script, re.MULTILINE))
    assert defined_there & defined_here <= {"main"}
    for name in ("content_hash", "load_record", "write_record", "pick_latest_stable", "find_git_bash", "hashlib", "urllib"):
        assert f"def {name}" not in script and f"import {name}" not in script
    # No run of six or more identical non-trivial lines.
    shared_lines = [l.strip() for l in shared.splitlines()]
    windows = {tuple(shared_lines[i : i + 6]) for i in range(len(shared_lines) - 5)}
    # The few lines that put stdout into UTF-8 and LF when run as a script are the same in both, on purpose.
    script_lines = [l.strip() for l in script.split('if __name__ == "__main__":')[0].splitlines()]
    for i in range(len(script_lines) - 5):
        window = tuple(script_lines[i : i + 6])
        if sum(1 for l in window if len(l) > 20) >= 4:
            assert window not in windows, window


def test_script_loads_the_shared_code_from_the_adjacent_sdd_init(sdd_update, sdd_init):
    assert sdd_update.sdd_init_path().resolve() == SDD_INIT_SCRIPT.resolve()
    shared = sdd_update.load_sdd_init()
    assert shared is sdd_init
    assert callable(shared.load_record) and callable(shared.content_hash)
