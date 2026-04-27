"""Enforce the project rule that no suppression comments appear in source.

If this test fails, the fix is to address the underlying lint/type issue in
the code, not to silence the checker. See ``AGENTS.md`` for the full policy.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = ("src", "tests", "scripts", "calibre-plugin")

FORBIDDEN_PATTERNS = {
    "noqa": re.compile(r"#\s*noqa\b", re.IGNORECASE),
    "type:ignore": re.compile(r"#\s*type\s*:\s*ignore\b", re.IGNORECASE),
    "fmt:off": re.compile(r"#\s*fmt\s*:\s*off\b", re.IGNORECASE),
    "fmt:on": re.compile(r"#\s*fmt\s*:\s*on\b", re.IGNORECASE),
    "ruff:noqa": re.compile(r"#\s*ruff\s*:\s*noqa\b", re.IGNORECASE),
}

# Files that *describe* the policy itself, and therefore mention the forbidden
# pragmas in plain prose or docstrings. They never execute Python lints.
ALLOWED_FILES = frozenset(
    {
        Path(__file__).relative_to(REPO_ROOT),
    }
)


def _iter_python_files():
    for top in SCAN_DIRS:
        root = REPO_ROOT / top
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def test_no_suppression_comments():
    offenders: list[tuple[Path, int, str]] = []
    for path in _iter_python_files():
        rel = path.relative_to(REPO_ROOT)
        if rel in ALLOWED_FILES:
            continue
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                for label, pattern in FORBIDDEN_PATTERNS.items():
                    if pattern.search(line):
                        offenders.append((rel, lineno, label))
    assert not offenders, "Forbidden suppression comments found (see AGENTS.md):\n" + "\n".join(
        f"  {path}:{line} — {kind}" for path, line, kind in offenders
    )
