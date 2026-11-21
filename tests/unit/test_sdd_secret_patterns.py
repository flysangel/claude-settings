"""sdd-grill (005), sdd-export (006) and sdd-rebuild (007) agree on what looks like a secret.

006 keeps its own copy of 005's patterns (it runs without 005), and 007 uses both scripts. These tests fail as soon
as one copy changes without the other. Every token below is made up; none is a real credential.
"""

from __future__ import annotations

import random
import re
import time

import pytest

# 005's patterns as they were before the URL pattern of both copies was rewritten for speed: the reference for
# what "looks like a secret" means. The rewritten pattern must match exactly the same texts.
REFERENCE_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])xox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"),
    re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@"),
    re.compile(r"(?i)(?<![A-Za-z])(password|secret|token|api[_-]?key)\s*[=:]\s*\S"),
]


def reference(text: str) -> bool:
    return any(pattern.search(text) for pattern in REFERENCE_PATTERNS)


GHP = "ghp_" + "Zq8FakeSame" * 2
URL = "https://bob:FAKEpw9@h.example.invalid/x"

SECRETS = [
    # The counterexamples of the review: a digit or "]" and a dot right before the scheme.
    "1.https://u:p@h",
    "[0].https://u:p@h",
    "步驟 1.https://bob:pw@h/",
    "target.principles[0].https://u:FAKEpw2@h.invalid/",
    "a.b.https://u:p@h",
    "x+https://u:p@h",
    "-https://u:p@h",
    "9https://u:p@h",
    "1.2.3.ftp://u:p@h",
    "+.-https://u:p@h",
    "1a://u:p@h",
    "a1+.-://u:p@h",
    "postgres://admin:FAKEpw@db.example.invalid/app",
    "（https://u:p@h）",
    "：https://u:p@h",
    "，https://u:p@h",
    "見https://u:p@h",
    "「https://u:p@h」",
    "\u200bhttps://u:p@h",
    "\ufeffhttps://u:p@h",
    "line one\nhttps://u:p@h",
    "a" * 5000 + "1.https://u:p@h",
    "https://u:p:q@h",
    URL,
    # The other patterns, after the same leading characters.
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIE",
    "token " + GHP,
    "1." + GHP,
    "[0]." + GHP,
    "（" + GHP + "）",
    "\u200b" + GHP,
    "github_pat_" + "A1_" * 8,
    "key sk-" + "b" * 24,
    "1.sk-" + "proj-abcdefghijklmnopqrstuvwx",
    "xoxb-" + "1234567890ab",
    "].xoxp-" + "1234567890ab",
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "1.AKIA" + "ABCDEFGHIJKLMNOP",
    "password=FAKEpw",
    "PASSWORD: FAKEpw",
    "the db password: FAKEpw",
    "1.password=FAKEpw",
    "[0].token:x",
    "密碼password=x",
    "secret = abc123",
    "SECRET=abc",
    "token: xyz",
    "token:abc123",
    "token\n=\nx",
    "api_key=abc",
    "api_key = xyz",
    "API-KEY: abc",
    "apikey=abc",
    "a.password=FAKEpw1.b",
    "x." + GHP + ".y",
]

ORDINARY = [
    "使用者輸入 password 後才能登入",
    "使用者輸入 password 後…",
    "token 過期造成同步失敗",
    "token 過期造成…",
    "API key 由環境變數提供",
    "secret 不得記錄在日誌",
    "password：至少 8 個字元",
    "設定 token 的有效期限",
    "https://example.com/path:8080@x",
    "使用密碼管理器 (password manager)",
    "password 欄位改由環境變數提供",
    "a perfectly ordinary sentence",
    "the_password_field_is_required",
    "configure the api key in settings",
    "token",
    "sk-short",
    "sk-learn is not a token",
    "averyveryveryverylongidentifierwithoutanythingsecret_1234567890",
    "使用者輸入密碼後登入。",
    "The tool needs an API key to call the service; the maintainer keeps it outside the project.",
    "Users sign in with a password.",
    "A token budget of 1000 per request.",
    "https://example.invalid/docs/page",
    "Secrets are stored in the operating system keychain.",
    "4f9c2a1b8e7d6c5b4a39281706f5e4d3c2b1a09f",
    "1.https://example.invalid/x",
    "[0].https://h/x:y@z",
    "1.://u:p@h",
    "].://u:p@h",
    "1234://u:p@h",
    "+.-://u:p@h",
    "://u:p@h",
    "見://u:p@h",
    "https://u@h",
    "https://:p@h",
    "https://u:@h",
    "https:// u:p@h",
    "https://u:p h@x",
    "https://u/p:q@h",
    "https\u200b://u:p@h",
    "https://u:p\n@h",
    "mypassword=x",
    "notoken: x",
    "token = ",
    "token:\n",
    "ghp_" + "a" * 19,
    "xghp_" + "a" * 24,
    "1sk-" + "b" * 24,
    "-----BEGIN PUBLIC KEY-----",
    "a" * 5000,
    "1." * 3000,
    "a://" * 2000,
]


def corpus() -> list[str]:
    """The fixed samples plus random texts built from the characters the patterns care about."""
    pieces = ["a", "Z", "1", ".", "+", "-", "]", "[", ":", "/", "@", " ", "\n", "\u200b", "見", "：", "https",
              "://", "u:p@h", "password", "=", "token", "ghp_", "a1B2" * 6, "sk-", "AKIA", "ABCDEFGHIJKLMNOP"]
    rng = random.Random(20261121)
    texts = list(SECRETS) + list(ORDINARY)
    for _ in range(4000):
        texts.append("".join(rng.choice(pieces) for _ in range(rng.randint(1, 12))))
    return texts


def test_the_two_copies_hold_the_same_patterns(sdd_grill, sdd_export):
    assert [(p.pattern, p.flags) for p in sdd_grill.SECRET_PATTERNS] == \
        [(p.pattern, p.flags) for p in sdd_export.SECRET_PATTERNS]


@pytest.mark.parametrize("text", SECRETS)
def test_secrets_are_found_by_both(sdd_grill, sdd_export, text):
    assert reference(text)
    assert sdd_grill.looks_like_secret(text) and sdd_export.looks_like_secret(text)


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_text_is_found_by_neither(sdd_grill, sdd_export, text):
    assert not reference(text)
    assert not sdd_grill.looks_like_secret(text) and not sdd_export.looks_like_secret(text)


def test_both_copies_agree_with_the_reference_on_every_sample(sdd_grill, sdd_export):
    texts = corpus()
    differ = [t for t in texts
              if not reference(t) == sdd_grill.looks_like_secret(t) == sdd_export.looks_like_secret(t)]
    assert differ == []
    # The random part is not trivially all one answer.
    found = sum(reference(t) for t in texts)
    assert 200 < found < len(texts) - 200


def test_line_scan_agrees_with_the_string_scan(sdd_grill, sdd_export):
    """006 scans files line by line; a line is a secret exactly when 005 would call that line a secret."""
    text = "\n".join(corpus())
    lines = text.split("\n")
    assert sdd_export.secret_lines(text) == [n for n, line in enumerate(lines, 1) if sdd_grill.looks_like_secret(line)]


@pytest.mark.parametrize("key", [GHP, URL, "password=FAKEpw", "a.password=FAKEpw1.b", "x." + GHP + ".y",
                                 "1.https://u:p@h", "sk-" + "b" * 24])
@pytest.mark.parametrize("holder", ["", "target", "target.principles[0]", "features[12]", "a.b[3].c"])
def test_a_secret_field_name_still_looks_like_one_inside_a_path(sdd_grill, sdd_export, key, holder):
    """The last safety net of the scripts checks whole paths; a secret name must not hide behind ']' or '.'."""
    path = f"{holder}.{key}" if holder else key
    assert sdd_grill.looks_like_secret(path) and sdd_export.looks_like_secret(path)


LARGE = 4 * 1024 * 1024


@pytest.mark.parametrize("name, text", [
    ("letters", "a" * LARGE),
    ("scheme characters", "a1+.-" * (LARGE // 5)),
    ("digits and dots", "1." * (LARGE // 2)),
    ("schemes without a password", "a://b:" * (LARGE // 6)),
    ("a scheme and a long user", "a://" + "b" * LARGE),
    ("a scheme and a long password", "a://b:" + "c:" * (LARGE // 2)),
    ("long whitespace after a keyword", "token" + " " * LARGE),
    ("many keywords", "token " * (LARGE // 6)),
    ("a long key header", "-----BEGIN " + "A " * (LARGE // 2)),
    ("short lines", "a.b-c 1.https://example.invalid/x\n" * (LARGE // 34)),
])
def test_scanning_megabytes_stays_linear(sdd_grill, sdd_export, name, text):
    """Several MiB in one line, or in many short lines, are scanned in a few seconds by both copies."""
    started = time.monotonic()
    assert sdd_export.secret_lines(text) == []
    assert not sdd_grill.looks_like_secret(text)
    assert time.monotonic() - started < 10, name
