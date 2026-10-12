#!/usr/bin/env python3
"""Check what claude plugin validate doesn't (CI and local runs use the same script).

1. The frontmatter name in skills/<dir>/SKILL.md matches the directory name
   (validate warns about a missing name but lets a mismatch with the directory name through), and its
   description is at most 1024 characters (claude.ai cuts a longer one when it syncs the plugin, while
   validate passes it)
2. No personal environment leaks into the public repo: absolute home directory paths and email
   addresses (noreply and example domains excluded). Extra blocked terms come from the environment
   variable BLOCKED_PATTERNS (newline-separated regexes; CI passes it from a repo secret). Writing the
   blocked terms in this file would itself leak them into the public repo
3. README pairs: the root and every plugins/<name>/ with a README.md also have a README.ja.md next to it,
   line 3 of each is the language switcher linking to the other, and README.md has no Hiragana or
   Katakana (Japanese text belongs in README.ja.md; Han alone is allowed for the switcher label)
4. With --base <ref> (CI on PRs): lines added since the base have no Japanese prose, i.e. no Hiragana /
   Katakana outside quotes. English is the base language (CLAUDE.md "Language"); only added lines are
   checked, so the Japanese data already in the repo doesn't need listing. Allowed: README.ja.md, files under
   tests/, evals/ or fixtures/, SKILL.md frontmatter (the description's Japanese trigger phrases), quoted text
   (`code`, 「quotes」, '...', "...": user phrases, old Japanese markers, string literals, regexes) and lines
   containing `ja-ok` (unquoted data such as a list of Japanese keywords)
"""
import os
import re
import subprocess
import sys

ROOT = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                      capture_output=True, text=True, check=True).stdout.strip()
FILES = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                       capture_output=True, text=True, check=True).stdout.split("\0")

INDEX = "--index" in sys.argv  # read staged content instead of the working tree (for pre-commit)
LEAKS = [
    # The brackets around the second o keep this line from matching itself
    (re.compile(r"/Users/[A-Za-z]|/home/[a-z]|/ro[o]t/"), "absolute home directory path"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|noreply\.|anthropic\.com|github\.com\b|example\.)"
                r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "email address"),
]
LEAKS += [(re.compile(p), "BLOCKED_PATTERNS")
          for p in os.environ.get("BLOCKED_PATTERNS", "").splitlines() if p.strip()]

README_EN = re.compile(r"(plugins/[^/]+/)?README\.md")
README_JA = re.compile(r"(plugins/[^/]+/)?README\.ja\.md")
KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\uff66-\uff9f]")  # Hiragana, Katakana, halfwidth Katakana


SWITCHER = {"README.md": "English | [日本語](README.ja.md)", "README.ja.md": "[English](README.md) | 日本語"}


DESCRIPTION_MAX = 1024


def description(frontmatter):
    """The description value: a one-line scalar, or a block scalar (| or >) folded to one line."""
    lines = frontmatter.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"description:\s*(.*)$", line)
        if not m:
            continue
        value = m.group(1).strip()
        if value[:1] in "|>":
            block = []
            for nxt in lines[i + 1:]:
                if nxt and not nxt[0].isspace():
                    break
                block.append(nxt.strip())
            return " ".join(b for b in block if b)
        return value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'" else value
    return ""


def has_switcher(name, text):
    # Line 3 (title, blank line, switcher) must be exactly the switcher, so a stray link elsewhere doesn't count
    lines = text.splitlines()
    return len(lines) >= 3 and lines[2].strip() == SWITCHER[name]


errors = []
for f in filter(None, FILES):
    path = os.path.join(ROOT, f)
    try:
        # Don't skip unreadable characters (so leaks can't slip through hidden in non-UTF-8 files)
        if INDEX:
            # pre-commit: what gets committed is the index. Reading the working tree would miss a leak
            # that was staged and then fixed only in the working tree
            text = subprocess.run(["git", "show", f":{f}"], cwd=ROOT, capture_output=True,
                                  check=True).stdout.decode("utf-8", errors="replace")
        else:
            text = open(path, encoding="utf-8", errors="replace").read()
    except (IsADirectoryError, FileNotFoundError, subprocess.CalledProcessError):
        continue
    if f.endswith("/SKILL.md") and "/skills/" in f:
        head = text.split("---")
        m = re.search(r"^name:\s*(\S+)", head[1] if len(head) > 2 else "", re.M)
        want = os.path.basename(os.path.dirname(f))
        if not m or m.group(1).strip("\"'") != want:
            errors.append(f"{f}: frontmatter name does not match the directory name '{want}'")
        desc = description(head[1] if len(head) > 2 else "")
        if len(desc) > DESCRIPTION_MAX:
            errors.append(f"{f}: frontmatter description is {len(desc)} characters (at most {DESCRIPTION_MAX})")
    m = README_EN.fullmatch(f)
    if m:
        if f"{m.group(1) or ''}README.ja.md" not in FILES:
            errors.append(f"{f}: README.ja.md is missing next to it")
        if not has_switcher("README.md", text):
            errors.append(f"{f}:3: line 3 must be the language switcher: {SWITCHER['README.md']}")
        kana = next((n for n, line in enumerate(text.splitlines(), 1) if KANA.search(line)), None)
        if kana:
            errors.append(f"{f}:{kana}: Hiragana/Katakana in README.md (Japanese text belongs in README.ja.md)")
    elif README_JA.fullmatch(f):
        m = README_JA.fullmatch(f)
        if f"{m.group(1) or ''}README.md" not in FILES:
            errors.append(f"{f}: README.md is missing next to it")
        if not has_switcher("README.ja.md", text):
            errors.append(f"{f}:3: line 3 must be the language switcher: {SWITCHER['README.ja.md']}")
    for n, line in enumerate(text.splitlines(), 1):
        for rx, what in LEAKS:
            if rx.search(line):
                errors.append(f"{f}:{n}: {what}")  # don't print the matched text (the log is public too)
# Single quotes count only as a literal, not as contractions: the opening quote follows a non-word character
# (or a string prefix such as r / b / f) and the closing one isn't followed by a word character. Backslash
# escapes inside '...' and "..." don't end the literal
QUOTED = re.compile(r"`[^`]*`|「[^」]*」|(?:(?<!\w)|(?<=(?<!\w)[rRbBuUfF]))'(?:\\.|[^'\\])*'(?!\w)|\"(?:\\.|[^\"\\])*\"")
LANG_EXEMPT = re.compile(r"(^|/)(README\.ja\.md$|tests/|evals/|fixtures/)")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def frontmatter_end(f):
    """Last line number of a SKILL.md frontmatter at HEAD (0 if none)."""
    try:
        lines = git("show", f"HEAD:{f}").splitlines()
    except subprocess.CalledProcessError:
        return 0
    if not lines or lines[0].strip() != "---":
        return 0
    return next((n for n, line in enumerate(lines[1:], 2) if line.strip() == "---"), 0)


if "--base" in sys.argv:
    base = git("merge-base", sys.argv[sys.argv.index("--base") + 1], "HEAD").strip()
    # Paths come from -z (never quoted); each file's diff is read on its own, and only lines after the first
    # @@ are content, so an added line starting with "++ " can't be mistaken for a file header
    for f in filter(None, git("diff", "--name-only", "-z", "--diff-filter=d", base, "HEAD").split("\0")):
        if LANG_EXEMPT.search(f):
            continue
        fm = frontmatter_end(f) if f == "SKILL.md" or f.endswith("/SKILL.md") else 0
        n = None
        for line in git("diff", "-U0", "--no-color", base, "HEAD", "--", f).splitlines():
            if line.startswith("@@"):
                n = int(re.search(r"\+(\d+)", line).group(1))
            elif n is not None and line.startswith("+"):
                text = line[1:]
                if not (n <= fm or "ja-ok" in text) and KANA.search(QUOTED.sub("", text)):
                    errors.append(f"{f}:{n}: Japanese outside quotes (write it in English, quote it, or add ja-ok to the line)")
                n += 1

# Don't print the location or count of BLOCKED_PATTERNS matches. If the public log showed which line
# matched, an external PR could probe candidate terms to guess internal names (see locations in the local pre-commit)
blocked = [e for e in errors if e.endswith(": BLOCKED_PATTERNS")]
if blocked and os.environ.get("HIDE_BLOCKED_LOCATIONS"):
    errors = [e for e in errors if e not in blocked] + ["some lines match internal names (BLOCKED_PATTERNS)"]

print("\n".join(errors) if errors else "OK")
sys.exit(1 if errors else 0)
