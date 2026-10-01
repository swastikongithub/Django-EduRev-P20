"""
Documentation integrity: every relative link and #anchor in the repository's Markdown resolves.

Anchors are checked against GitHub's heading slugs (lower-case, punctuation dropped, spaces to
hyphens, "-1", "-2" for repeats). Links inside fenced code blocks and external URLs are ignored.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", "staticfiles", ".devdb", "__pycache__"}
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def markdown_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if not any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts))


def _prose_lines(path: Path):
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if not fenced:
            yield line


def slug(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)  # inline code keeps its text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep their label
    text = re.sub(r"[*~]", "", text)  # emphasis markers; underscores are kept, as GitHub does
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for line in _prose_lines(path):
        m = HEADING.match(line)
        if not m:
            continue
        base = slug(m.group(2))
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.add(base if n == 0 else f"{base}-{n}")
    return out


def broken_links() -> list[str]:
    cache: dict[Path, set[str]] = {}
    problems = []
    for md in markdown_files():
        for line in _prose_lines(md):
            for target in LINK.findall(line):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http:, https:, mailto:
                    continue
                file_part, _, anchor = target.partition("#")
                dest = (md.parent / file_part).resolve() if file_part else md
                where = f"{md.relative_to(ROOT)} -> {target}"
                if not dest.exists():
                    problems.append(f"{where}: missing file")
                    continue
                if anchor and dest.suffix == ".md":
                    found = cache.setdefault(dest, anchors(dest))
                    if anchor not in found:
                        problems.append(f"{where}: no heading with that anchor")
    return problems


def test_there_is_documentation_to_check():
    names = {p.relative_to(ROOT).as_posix() for p in markdown_files()}
    for required in (
        "README.md",
        "docs/known-issues.md",
        "docs/roles.md",
        "docs/guide-admin.md",
        "docs/guide-user.md",
        "docs/traceability.md",
        "docs/security-review.md",
    ):
        assert required in names


def test_every_internal_link_and_anchor_resolves():
    problems = broken_links()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("Redis is down", "redis-is-down"),
        ("P20 §22 Acceptance criteria", "p20-22-acceptance-criteria"),
        ("`DJANGO_SECRET_KEY` rotation", "django_secret_key-rotation"),
        ("Signing in and MFA", "signing-in-and-mfa"),
        ("CES §1.4 Security baseline", "ces-14-security-baseline"),
    ],
)
def test_slugs_follow_github(heading, expected):
    assert slug(heading) == expected
