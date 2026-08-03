#!/usr/bin/env python3
"""Fail CI on high-confidence secrets in release-candidate files.

This intentionally scans Git's tracked and unignored-untracked file set. Local
``config.ini``, memories, logs, models, and generated output are ignored and are
never opened. The detector favors well-known credential prefixes and private
key headers; it is a release backstop, not a substitute for provider-side
secret scanning or the completed full-history review.
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


MAX_TEXT_BYTES = 2 * 1024 * 1024

# Split distinctive literals so this scanner does not report its own source.
TOKEN_PATTERNS = (
    ("private key", re.compile("-----BEGIN " + r"(?:RSA |EC |DSA |OPENSSH )?" + "PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,255}")),
    ("GitHub fine-grained token", re.compile("github" + r"_pat_[A-Za-z0-9_]{50,255}")),
    ("AWS access key", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("OpenAI-style key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("Hugging Face token", re.compile(r"hf_[A-Za-z0-9]{30,}")),
    ("Stripe live key", re.compile(r"[rs]k_live_[A-Za-z0-9]{20,}")),
    ("npm token", re.compile(r"npm_[A-Za-z0-9]{36,}")),
)

ASSIGNMENT = re.compile(
    r"(?im)^\s*(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password)\s*[:=]\s*['\"]?([^\s'\"#;]{16,})"
)

PLACEHOLDER_WORDS = (
    "change_me", "changeme", "example", "fake", "for_local", "not_needed",
    "placeholder", "replace_me", "test_only", "your_", "xxxxx",
)


def _entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length)
                for count in counts.values())


def _looks_like_real_assignment(value: str) -> bool:
    lowered = value.casefold()
    if any(word in lowered for word in PLACEHOLDER_WORDS):
        return False
    return len(set(value)) >= 8 and _entropy(value) >= 3.5


def release_candidate_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [Path(raw.decode("utf-8"))
            for raw in result.stdout.split(b"\0") if raw]


def scan_text(text: str) -> list[tuple[str, int]]:
    findings: list[tuple[str, int]] = []
    for name, pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            findings.append((name, text.count("\n", 0, match.start()) + 1))
    for match in ASSIGNMENT.finditer(text):
        if _looks_like_real_assignment(match.group(1)):
            findings.append((
                "high-entropy credential assignment",
                text.count("\n", 0, match.start()) + 1,
            ))
    return findings


def main() -> int:
    findings: list[tuple[Path, str, int]] = []
    for path in release_candidate_paths():
        if not path.is_file() or path.stat().st_size > MAX_TEXT_BYTES:
            continue
        raw = path.read_bytes()
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend((path, name, line) for name, line in scan_text(text))

    if findings:
        for path, name, line in findings:
            print(f"{path.as_posix()}:{line}: possible {name} (value redacted)")
        print(f"Secret scan failed with {len(findings)} high-confidence finding(s).")
        return 1

    print("Secret scan passed: no high-confidence credentials in release candidates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
