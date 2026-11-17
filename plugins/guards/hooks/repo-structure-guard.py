#!/usr/bin/env python3
"""PreToolUse hook: repo-structure-guard for Write (enforces repo layout rules; opt-in).

**This script holds none of the values it judges by** (allowed file names, the standard
subfolder set, script extensions, exemptions). It reads the `<!-- guard:… -->` blocks of a
rule file at run time. It uses the first rule file found, in this order, and does nothing if none exists:
  1. The environment variable `REPO_STRUCTURE_SPEC` (if set, only this is used; if it points nowhere, do nothing)
  2. `.claude/rules/repo-structure.md` on the default branch (origin/<default>) of the repo being written to (per-repo
     rules). Read from the default branch, not the working tree, so a branch cannot loosen the rule it is judged by:
     a change takes effect once it is merged. Without an origin remote the working tree is read (with a note on stderr)
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
import subprocess
import sys

SPEC_RELPATH = os.path.join(".claude", "rules", "repo-structure.md")
# Git variables that select a repository are dropped, so `git -C <write target's repo>` really reads that repo
_REPO_SELECT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")
GIT_ENV = {**{k: v for k, v in os.environ.items() if k not in _REPO_SELECT_VARS}, "GIT_TERMINAL_PROMPT": "0"}


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


def _git(root: str, *args: str):
    """(returncode, stdout) of a git command in root. Never prompts; (1, "") on timeout."""
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=5, env=GIT_ENV)
    except (subprocess.TimeoutExpired, OSError):
        return 1, ""
    return r.returncode, r.stdout


def _has_ref(root: str, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", ref)[0] == 0


def default_branch(root: str) -> str:
    """The default branch name: the local origin/HEAD (no network; this runs on every new file under docs/ or scripts/),
    else what origin reports (ls-remote, 5 s), else origin/main or origin/master. A branch's mere existence is only the
    last guess, since a pushed `main` that is not the default would otherwise supply the rules."""
    rc, ref = _git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and ref.strip().startswith("origin/"):
        return ref.strip()[len("origin/"):]
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", _git(root, "ls-remote", "--symref", "origin", "HEAD")[1], re.M)
    if m:
        return m.group(1)
    if not _has_ref(root, "refs/remotes/origin/main") and _has_ref(root, "refs/remotes/origin/master"):
        return "master"
    return "main"


def base_spec(root: str):
    """The repo's rule file as (label, text) from the default branch. None when it is not there.
    Read from origin/<default branch>, not the working tree, so a branch cannot loosen the rule it is judged by."""
    name = default_branch(root)
    ref = f"refs/remotes/origin/{name}"
    if not _has_ref(root, ref):
        try:  # fetch it once; a stale origin/<default> is fine (the older rules apply)
            # an explicit destination, so a single-branch clone (whose refspec does not cover name) still gets the ref
            subprocess.run(["git", "-C", root, "fetch", "--quiet", "origin", "--", f"+refs/heads/{name}:{ref}"], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=5, env=GIT_ENV)
        except (subprocess.TimeoutExpired, OSError):
            pass
        if not _has_ref(root, ref):
            print(f"repo-structure-guard: cannot read origin/{name}; skipping the repo's rule file", file=sys.stderr)
            return None
    rc, text = _git(root, "show", f"{ref}:{SPEC_RELPATH.replace(os.sep, '/')}")
    return (f"origin/{name}:{SPEC_RELPATH}", text) if rc == 0 else None


def resolve_spec(path: str):
    """The rules that apply to the write target path, as (label, text). text None means "read the file at label".
    None if there are none (do nothing)."""
    env = os.environ.get("REPO_STRUCTURE_SPEC")
    if env:
        return os.path.expanduser(env), None
    root = repo_root(path)
    if root:
        if _git(root, "remote", "get-url", "origin")[0] == 0:
            spec = base_spec(root)
            if spec:
                return spec
        else:  # no origin, so no PR can exist: the working tree is all there is
            repo = os.path.join(root, SPEC_RELPATH)
            if os.path.exists(repo):
                print(f"repo-structure-guard: no origin remote: reading {SPEC_RELPATH} from the working tree", file=sys.stderr)
                return repo, None
    user = os.path.join(os.path.expanduser("~"), SPEC_RELPATH)
    if os.path.exists(user):
        return user, None
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

    spec = resolve_spec(norm)
    if spec is None:
        sys.exit(0)  # no rule file = this repo / this user does not use repo layout rules
    SPEC, spec_text = spec
    if spec_text is None:
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
