#!/usr/bin/env python3
"""SessionStart hook: briefly flags stale knowledge files.

Why it exists (a real incident, 2026-09-21):
  The top of one of the user's reference documents carried a hand-written note:
  "⚠️ The 'closing is manual' rule in this document was withdrawn on 2026-09-21". It was **a correction a human
  noticed and pasted by hand**; nothing structural caught it. Another knowledge base kept last_reviewed /
  review_after in its INDEX.md and a skill checked freshness, but `~/.claude` had no such mechanism.
  This builds "a human notices it has gone stale" into the knowledge itself, so freshness is guaranteed by
  structure rather than by the operator's goodwill.

**Strength is WARN only. It never BLOCKs** (serious things are stopped; things still growing are just flagged).
  Stopping a session because knowledge is old is too much; the only things the stopped side can do are
  delete the file or push the date out.

Design promises:
  - **Completely silent when nothing is stale** (exit 0, no output), since it runs every session
  - **Never blocks session start, whatever happens**. Broken frontmatter YAML or a missing file is caught,
    and it exits 0
  - **Files without last_reviewed are also listed, as "freshness not set"**. A missing setting is harder to spot
    than an expired one (it would never warn)
  - The initial value is a mechanical bootstrap from the last-edited date, not "the day someone re-read and
    confirmed it", so the WARN text says so (otherwise it would be mistaken for "confirmed")
"""
import datetime
import json
import os
import re
import sys

ROOT = os.path.expanduser("~/.claude")
TARGETS = [
    ("rules", os.path.join(ROOT, "rules"), "*.md"),
    ("reference", os.path.join(ROOT, "reference"), "*.md"),
    ("skills", os.path.join(ROOT, "skills"), "*/SKILL.md"),
]
FM_RE = re.compile(r"\A---\n(.*?\n)---\n", re.S)
DATE_RE = re.compile(r"^review_after:\s*(20\d\d-\d\d-\d\d)\s*$", re.M)
HAS_REVIEWED = re.compile(r"^last_reviewed:\s*20\d\d-\d\d-\d\d\s*$", re.M)
MAX_LIST = 12


def iter_files():
    import glob
    for label, base, pat in TARGETS:
        for p in sorted(glob.glob(os.path.join(base, pat))):
            yield label, p


def main() -> None:
    today = datetime.date.today()
    expired, unset = [], []

    for label, path in iter_files():
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                head = f.read(4096)
        except OSError:
            continue
        m = FM_RE.match(head)
        fm = m.group(1) if m else ""
        rel = os.path.relpath(path, ROOT)

        if not HAS_REVIEWED.search(fm):
            unset.append(rel)
            continue
        d = DATE_RE.search(fm)
        if not d:
            unset.append(rel)
            continue
        try:
            due = datetime.date.fromisoformat(d.group(1))
        except ValueError:
            unset.append(rel)
            continue
        if today > due:
            expired.append((rel, (today - due).days))

    if not expired and not unset:
        sys.exit(0)  # completely silent when nothing is stale

    lines = ["[knowledge freshness]"]
    if expired:
        expired.sort(key=lambda x: -x[1])
        lines.append(f"{len(expired)} file(s) past review_after:")
        lines += [f"  - {rel} ({days} days overdue)" for rel, days in expired[:MAX_LIST]]
        if len(expired) > MAX_LIST:
            lines.append(f"  - (and {len(expired) - MAX_LIST} more)")
    if unset:
        lines.append(f"{len(unset)} file(s) with no freshness set:")
        lines += [f"  - {rel}" for rel in unset[:MAX_LIST]]
        if len(unset) > MAX_LIST:
            lines.append(f"  - (and {len(unset) - MAX_LIST} more)")
    lines += [
        "",
        "This is a warning, not a stop. **No need to fix it right now.**",
        "But if you rely on any of these files in this session, read them with suspicion: "
        "check that what they say still matches reality.",
        "Once you have re-read one and confirmed it is correct, set `last_reviewed` to today "
        "and move `review_after` further out.",
        "(The initial `last_reviewed` is a mechanical bootstrap from the last-edited date, "
        "not a day someone re-read and confirmed it.)",
    ]

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines),
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # never stop session start, whatever happens
