"""The patterns that mark a private value, shared by check-repo.py (file contents) and scan-text.py
(issue / PR text), so the two scans cannot drift.

- Built-ins: an absolute home directory path and an e-mail address (noreply and example domains excluded)
- BLOCKED_PATTERNS: newline-separated regexes from the environment (CI passes a repo secret, the
  pre-commit hook a local file). Blank lines are skipped and each entry goes to re.compile as is, so
  case-insensitivity is written into the pattern as (?i). Writing the blocked terms in this repo would
  itself leak them

Importing this module runs nothing (no git, no network).
"""
import os
import re

BUILTINS = [
    # The brackets around the second o keep this line from matching itself
    (re.compile(r"/Users/[A-Za-z]|/home/[a-z]|/ro[o]t/"), "absolute home directory path"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|noreply\.|anthropic\.com|github\.com\b|example\.)"
                r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "email address"),
]


class InvalidPattern(ValueError):
    """A BLOCKED_PATTERNS entry that is not a regex. The message carries the entry's number (counted
    over the non-blank lines, from 1) and never the entry itself: the log may be public."""

    def __init__(self, index):
        super().__init__(f"BLOCKED_PATTERNS entry #{index} is not a valid regex")
        self.index = index


def blocked(source=None):
    """The compiled BLOCKED_PATTERNS entries (source defaults to the environment variable)."""
    if source is None:
        source = os.environ.get("BLOCKED_PATTERNS", "")
    out = []
    for n, p in enumerate((p for p in source.splitlines() if p.strip()), 1):
        try:
            out.append(re.compile(p))
        except re.error:
            raise InvalidPattern(n) from None
    return out


def leaks(source=None):
    """[(regex, what it is)]: the built-ins, then every BLOCKED_PATTERNS entry."""
    return BUILTINS + [(rx, "BLOCKED_PATTERNS") for rx in blocked(source)]
