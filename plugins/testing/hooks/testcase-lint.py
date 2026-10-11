#!/usr/bin/env python3
"""PostToolUse hook: mechanically check that a test case artifact follows the style guide.

The matcher is "Edit|Write" (**it can only match tool names**, so it cannot filter by path).
Files out of scope exit 0 within a few ms with no output = completely silent.

Why it is needed:
  Structuring the knowledge only gets you to "the rules are known"; whether they are followed is
  still up to the AI. Only checking the artifact mechanically every time it is written makes the rules "impossible to break".

**Why the scope is narrow (a constraint of living globally)**:
  Put in a project's .claude/settings.json, a hook like this hits only that project's test artifacts.
  Shipped in a plugin it hits **every Write/Edit in every repo**, so a single vague word in an ordinary
  document would block, and constant names in implementation code would WARN every time.
  So it is **opt-in**:
    1. extension .feature / .gherkin
    2. .md files whose frontmatter has `testcase: true`
  Anything else exits 0 immediately. On top of that, nothing is checked if the body has no "Scenario" or "シナリオ" (a second safety valve).
  * These two conditions put style-guide.md itself out of scope even though it **lists the forbidden words as examples**
    (.md without the testcase flag). The structure prevents it from blocking on itself.

**Why the forbidden words are not in this file**:
  The forbidden words are not defined in this script; it reads the SPEC (style guide) at run time.
  With two definitions, one gets updated and the other drifts. Add one line to the SPEC and the hook changes from the next run.

Strength:
  - vague words      → BLOCK (exit 2). Nobody but the author can tell what to check
  - internal terms   → WARN. The UI-terms guide to check against is project-specific, so there is none globally.
                       Blocking with nothing to check against would stop work with no way to fix it

Design promises:
  - **Out-of-scope files are completely silent** (exit 0, no output), since it runs on every Edit/Write
  - **If the SPEC cannot be read, do not pass silently.** Inject a message saying it was not checked
    (a silent pass would be mistaken for "checked"; same policy as design-lint.py). But do not BLOCK
  - Whatever happens, never break the Write itself
"""
import json
import os
import re
import sys

# The style guide of the bundled testcase-generator skill (under skills/, next to hooks/)
SPEC = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "skills", "testcase-generator", "references", "style-guide.md",
))
TARGET_EXT = (".feature", ".gherkin")
MAX_BYTES = 512 * 1024  # do not read huge files (prefer unchecked over misfiring)


def has_word(word: str, line: str) -> bool:
    """ASCII words match as whole words, ignoring case; other words (Japanese) as substrings."""
    if word.isascii():
        return re.search(rf"\b{re.escape(word)}\b", line, re.I) is not None
    return word in line


def read_block(spec_text: str, tag: str) -> list[str]:
    """Extract the "- " lines from <!-- lint:TAG --> ... <!-- /lint:TAG --> in the SPEC."""
    m = re.search(
        rf"<!--\s*lint:{re.escape(tag)}\s*-->(.*?)<!--\s*/lint:{re.escape(tag)}\s*-->",
        spec_text,
        re.S,
    )
    if not m:
        return []
    return [
        line.strip()[2:].strip()
        for line in m.group(1).splitlines()
        if line.strip().startswith("- ")
    ]


def is_target(path: str) -> bool:
    if path.lower().endswith(TARGET_EXT):
        return True
    if not path.lower().endswith(".md"):
        return False
    # only frontmatter testcase: true counts (writing it somewhere in the body does not)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(2048)
    except OSError:
        return False
    fm = re.match(r"^---\n(.*?)\n---", head, re.S)
    return bool(fm and re.search(r"^testcase:\s*true\s*$", fm.group(1), re.M))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not str(data.get("tool_name", "")).endswith(("Edit", "Write")):
        sys.exit(0)

    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path or not os.path.isfile(path):
        sys.exit(0)
    try:
        if os.path.getsize(path) > MAX_BYTES:
            sys.exit(0)
    except OSError:
        sys.exit(0)

    if not is_target(path):
        sys.exit(0)  # out of scope: completely silent

    try:
        body = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        sys.exit(0)
    if not re.search(r"Scenario|シナリオ", body):
        sys.exit(0)  # no Gherkin (English or Japanese keywords), nothing to check

    try:
        spec_text = open(SPEC, encoding="utf-8", errors="replace").read()
        vague = read_block(spec_text, "vague-words")
        patterns = read_block(spec_text, "internal-term-patterns")
    except OSError as e:
        warn(
            f"[Test case check NOT RUN] {path}\n"
            f"Could not read the style guide ({type(e).__name__}): {SPEC}\n"
            f"The forbidden-word definitions are unavailable, so nothing was checked. **Do not treat this as checked.**"
        )
    if not vague and not patterns:
        warn(
            f"[Test case check NOT RUN] {path}\n"
            f"Could not extract the forbidden-word blocks from {SPEC} (broken markers or a format change).\n"
            f"Nothing was checked, so **do not treat this as checked.**"
        )

    lines = body.splitlines()
    vague_hits = [
        (i, w, ln.strip())
        for i, ln in enumerate(lines, 1)
        for w in vague
        if has_word(w, ln)
    ]
    internal_hits = []
    for pat in patterns:
        try:
            rx = re.compile(pat)
        except re.error:
            continue  # keep checking the rest even if a regex in the SPEC is broken
        internal_hits += [
            (i, pat, ln.strip()) for i, ln in enumerate(lines, 1) if rx.search(ln)
        ]

    if vague_hits:
        msg = [f"🛑 Test case check BLOCK: {path}", "", "**Vague words remain.**"]
        msg += [f"  L{i}: \"{w}\" — {txt[:80]}" for i, w, txt in vague_hits[:15]]
        if len(vague_hits) > 15:
            msg.append(f"  ({len(vague_hits) - 15} more)")
        msg += [
            "",
            "Then must state something a person can judge true or false on the spot. "
            "With the words above, nobody but the author can tell what to check.",
            "Rewrite them as concrete on-screen text, numbers or statuses.",
            f"(forbidden words are defined in: {SPEC})",
        ]
        if internal_hits:
            msg += ["", f"* There are also {len(internal_hits)} suspected internal terms (see the WARN below)."]
            msg += [f"  L{i}: {txt[:80]}" for i, _, txt in internal_hits[:5]]
        print("\n".join(msg), file=sys.stderr)
        sys.exit(2)

    if internal_hits:
        msg = [f"⚠️ Test case check WARN: {path}", "", "**Internal terms may remain.**"]
        msg += [f"  L{i}: {txt[:80]}" for i, _, txt in internal_hits[:10]]
        if len(internal_hits) > 10:
            msg.append(f"  ({len(internal_hits) - 10} more)")
        msg += [
            "",
            "Test cases are read by manual testers who have not seen the code. "
            "With API paths or internal constant names, they cannot tell what to operate on screen.",
            "If the project has a UI-terms guide "
            "($CLAUDE_PROJECT_DIR/.claude/knowledge/ui-terms.md), check against it.",
            "If not, do not invent names; leave them under \"Points to confirm\".",
        ]
        warn("\n".join(msg))

    sys.exit(0)  # stay quiet when clean


def warn(text: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
