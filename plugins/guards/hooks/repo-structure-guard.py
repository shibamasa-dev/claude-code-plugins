#!/usr/bin/env python3
"""PreToolUse hook: repo-structure-guard for Write (enforces repo layout rules; opt-in).

**This script holds none of the values it judges by** (allowed file names, the standard
subfolder set, script extensions, exemptions). It reads the `<!-- guard:… -->` blocks of a
rule file at run time. It uses the first rule file found, in this order, and does nothing if none exists:
  1. The environment variable `REPO_STRUCTURE_SPEC` (if set, only this is used; if it points nowhere, do nothing)
  2. `.claude/rules/repo-structure.md` in the repo being written to (per-repo rules; commit it to share with the team)
  3. `~/.claude/rules/repo-structure.md` (the user's rules)
A sample lives in the plugin's `examples/repo-structure.md` (never read as rules; copy and edit it to use it).

Why (2026-09-23):
  The same convention used to exist twice, worded differently, in prose (rules) and in code (this file),
  and **they had actually drifted** — the skill-layout exemption went into the code only, after two
  incidents (166 false positives on 2026-09-17, a false positive on a distributed skill on 2026-09-21),
  and five weeks later the prose still did not mention it. Readers of the prose understood
  "never directly under scripts/", while the code let skill folders through.
  Now editing one line of a block changes both the hook's behavior and its deny message.

Enforcement points (values live in the SPEC, not here):
  - Deny creating a new .md directly under docs/ (allowed names: guard:docs-allow-filenames)
  - Deny creating a new script directly under scripts/ (extensions: guard:script-extensions)
  - Exemptions are switched on or off by their IDs in guard:exemptions

Overwriting an existing file is out of scope (the rule is "don't add new ones"; existing docs can be moved when touched).
The matcher is Write only (Edit targets existing files, so it is not registered).

Design promises:
  - **No rule file, no action.** The repo layout is up to the user and the repo (opt-in since 2026-10-06).
  - **If the SPEC exists but can't be read, don't block the Write.** Stopping work because the guard
    is broken is too much. But passing silently would suggest "layout checked", so inject a note
    that the check did not run (same policy as design-lint.py).
"""
import json
import os
import re
import sys

SPEC_RELPATH = os.path.join(".claude", "rules", "repo-structure.md")


def repo_root(path: str):
    """Root of the repo containing path (the nearest ancestor with .git). None outside a repo."""
    d = os.path.dirname(path)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def resolve_spec(path: str):
    """The rule file that applies to the write target path. None if there is none (do nothing)."""
    env = os.environ.get("REPO_STRUCTURE_SPEC")
    if env:
        return os.path.expanduser(env)
    root = repo_root(path)
    if root:
        repo = os.path.join(root, SPEC_RELPATH)
        if os.path.exists(repo):
            return repo
    user = os.path.join(os.path.expanduser("~"), SPEC_RELPATH)
    if os.path.exists(user):
        return user
    return None


def read_block(spec_text: str, tag: str) -> list:
    """Extract the "- " lines from <!-- guard:TAG --> ... <!-- /guard:TAG --> in the SPEC."""
    m = re.search(
        rf"<!--\s*guard:{re.escape(tag)}\s*-->(.*?)<!--\s*/guard:{re.escape(tag)}\s*-->",
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


def split_kv(entries: list) -> list:
    """Split `key: description` lines into (key, description). Without `:` the description is empty."""
    out = []
    for e in entries:
        k, sep, v = e.partition(":")
        out.append((k.strip(), v.strip() if sep else ""))
    return out


def repo_parts(path: str) -> list:
    """Split path into components relative to the repo root (the nearest ancestor with .git).

    This keeps components of the checkout location (e.g. /work/skills/proj) from wrongly
    triggering an exemption. Outside a repo, the absolute path is split as is.
    """
    root = repo_root(path)
    return os.path.relpath(path, root).split(os.sep) if root else path.split(os.sep)


def allow_with_notice(text: str) -> None:
    """Don't block the Write; only report that the check could not run."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": text,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Write":
        sys.exit(0)
    fp = (data.get("tool_input") or {}).get("file_path", "")
    if not fp or os.path.exists(fp):
        sys.exit(0)  # overwriting an existing file is out of scope

    norm = os.path.normpath(fp)
    parts = norm.split(os.sep)
    parent = os.path.basename(os.path.dirname(norm))
    name = os.path.basename(norm)
    ext = os.path.splitext(name)[1].lower()

    # Neither docs/ nor scripts/: no need to read the SPEC (this runs on every Write, so exit early)
    if parent not in ("docs", "scripts"):
        sys.exit(0)

    SPEC = resolve_spec(norm)
    if SPEC is None:
        sys.exit(0)  # no rule file = this repo / this user does not use repo layout rules
    try:
        spec_text = open(SPEC, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        sys.exit(0)  # the env var points to a missing path = explicitly turned off
    except OSError as e:
        allow_with_notice(
            f"[repo-structure guard NOT RUN] {fp}\n"
            f"Could not read the rules ({type(e).__name__}): {SPEC}\n"
            f"The layout rules were not checked. **Do not treat this write as layout-checked.**"
        )

    allow_names = read_block(spec_text, "docs-allow-filenames")
    subfolders = split_kv(read_block(spec_text, "docs-subfolders"))
    script_ext = {e.lower() for e in read_block(spec_text, "script-extensions")}
    exemptions = {k for k, _ in split_kv(read_block(spec_text, "exemptions"))}

    if not (allow_names and subfolders and script_ext):
        allow_with_notice(
            f"[repo-structure guard NOT RUN] {fp}\n"
            f"Could not extract the guard blocks from {SPEC} (broken markers or a changed format).\n"
            f"The layout rules were not checked. **Do not treat this write as layout-checked.**"
        )

    # ---- Exemptions (switched on or off by IDs in the SPEC)
    # A skill correctly keeps its scripts directly under `<skill>/scripts/`, so skip those.
    if "path-component-skills" in exemptions and parent == "scripts" and "skills" in repo_parts(norm):
        sys.exit(0)
    if "sibling-skill-md" in exemptions:
        parent_dir = os.path.dirname(norm)
        if os.path.basename(parent_dir) == "scripts" and os.path.exists(
                os.path.join(os.path.dirname(parent_dir), "SKILL.md")):
            sys.exit(0)

    reason = None
    if parent == "docs" and ext == ".md" and name not in allow_names:
        nav = " / ".join(f"{q}→{k}" for k, q in subfolders if q)
        reason = (
            f"🛑 repo-structure-guard: don't put .md files directly under docs/"
            f" (only {', '.join(allow_names)} allowed)."
            f" Use one of the subfolders {' '.join(k + '/' for k, _ in subfolders)}"
            f" ({nav})."
        )
    elif parent == "scripts" and ext in script_ext:
        reason = (
            "🛑 repo-structure-guard: don't put scripts directly under scripts/."
            " Use a subfolder per feature or domain (e.g. scripts/scheduler/)."
        )

    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason + f"\n(Source of the rules: {SPEC})",
            }
        }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
