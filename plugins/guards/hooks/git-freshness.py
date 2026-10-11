#!/usr/bin/env python3
"""PostToolUse hook: a generic dispatcher that brings the local merge-target branch up to origin after a merge.

Why PostToolUse:
  A PreToolUse permissionDecisionReason also reaches Claude's context, but **only by blocking
  the tool** (the additionalContext field exists only from PostToolUse on). The merge has
  already happened and there is nothing to block, so PostToolUse additionalContext is right here.
  Conversely, "committing on top of a stale branch" should be stopped before it happens, so
  rule_main_commit_freshness in bash-guard.py (PreToolUse) handles it with a deny.
  **bash-guard blocks; this hook informs.**

Why it is needed:
  Merges happen on the remote, so the local checkout does not follow automatically. Scheduled
  jobs or daemons that run that checkout directly keep running old code until someone pulls.
  It's not "live once merged" but "live once merged and pulled locally".

Adding a rule = write one function and register it in RULES (no extra hook registration).
Uses the same RULES pattern as bash-guard.py.

Current rules:
  1. post-merge-pull : after a merge, if the branch checked out locally is the PR's merge target
                       and is behind origin, fast-forward it with --ff-only. If that goes through
                       cleanly, do it and report; if not, **leave it alone** and only inject the
                       situation. The merge target is determined without hard-coding branch names:
                       - GitHub connector (mcp__*__merge_pull_request): whether the merge commit SHA
                         from the result landed in origin of the local branch. Acts only when the cwd's
                         origin is the merged owner/repo (merging another repo's PR leaves the checkout alone)
                       - gh pr merge: baseRefName from `gh pr view`; if unavailable, the repo's default branch
                       - git merge: the repo's default branch (origin/HEAD)

Design promises:
  - **Never auto-stash.** A conflicting stash pop silently wrecks work. If ff-only refuses,
    inject the situation (commits behind, files with uncommitted changes) and hand the decision to Claude/the user.
  - **Completely silent when all is well** (exit 0, no output). This runs on every Bash call.
  - Judge by git's own state (from the connector result, only the merge commit SHA is used).
"""
import json
import os
import re
import shlex
import subprocess
import sys

_CWD = None
_RESPONSE = None

MERGE_RE = re.compile(r"\b(gh\s+pr\s+merge\b|git\s+merge(?!-)(?!\s+--(abort|continue|quit)))")
COMMIT_RE = re.compile(r"\bgit\s+commit\b")


def inject(context: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }


def _git(args, cwd, timeout=15):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def _current_branch(cwd):
    r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return r.stdout.strip() if r.returncode == 0 else None


def _remote_default(cwd):
    """The default branch origin reports right now (ls-remote, read-only). Asked first because the local
    origin/HEAD is not updated by fetch. None if unreachable or auth is needed (don't make anyone wait)."""
    try:
        r = subprocess.run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL,
                           text=True, timeout=5, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (subprocess.TimeoutExpired, OSError):
        return None
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", r.stdout, re.M) if r.returncode == 0 else None
    return m.group(1) if m else None


def _default_branch(cwd):
    """The repo's default branch. Ask origin; if unreachable, the local origin/HEAD; failing that, whichever of origin/main or origin/master exists."""
    name = _remote_default(cwd)
    if name:
        return name
    r = _git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd, timeout=5)
    name = r.stdout.strip() if r.returncode == 0 else ""
    if name.startswith("origin/"):
        return name[len("origin/"):]
    for cand in ("main", "master"):
        if _git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{cand}"], cwd, timeout=5).returncode == 0:
            return cand
    return None


def _repo_state(cwd, branch):
    """Return (behind, dirty_files). None if it can't be determined."""
    # fetch is best-effort (offline just passes through = stays out of the way)
    _git(["fetch", "--quiet", "origin", "--", branch], cwd)
    r = _git(["rev-list", "--count", f"HEAD..origin/{branch}"], cwd)
    if r.returncode != 0:
        return None
    try:
        behind = int(r.stdout.strip() or "0")
    except ValueError:
        return None
    r = _git(["status", "--porcelain"], cwd)
    dirty = [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []
    return behind, dirty


def _origin_slug(cwd):
    """origin's owner/repo (lowercase). None if not GitHub."""
    r = _git(["config", "--get", "remote.origin.url"], cwd, timeout=5)
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def _origin_host_slug(cwd):
    """origin's (host, owner/repo) (lowercase). Also reads hosts other than github.com, such as GitHub Enterprise."""
    r = _git(["config", "--get", "remote.origin.url"], cwd, timeout=5)
    url = r.stdout.strip() if r.returncode == 0 else ""
    m = (re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url, re.I)
         or re.match(r"^(?:[^@/]+@)?([^/:]+):(.+)$", url))
    if not m:
        return None
    parts = re.sub(r"(?:\.git)?/?$", "", m.group(2)).split("/")
    return (m.group(1).lower(), "/".join(parts[-2:]).lower()) if len(parts) >= 2 else None


def _same_repo(cwd, repo):
    """Whether gh's -R ([HOST/]OWNER/REPO) is the same repo as the cwd's origin.
    Without HOST, compare owner/repo only (`-R O/R` in a GitHub Enterprise clone counts as the same repo)."""
    origin = _origin_host_slug(cwd)
    parts = repo.strip().rstrip("/").split("/")
    if not origin or len(parts) not in (2, 3):
        return False
    if len(parts) == 3 and parts[0].lower() != origin[0]:
        return False
    return "/".join(parts[-2:]).lower() == origin[1]


# ------------------------------------------------------------ post-merge-pull
GH_MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b([^;&|\n]*)")
# gh pr merge flags that take a value (so the value isn't mistaken for the selector)
GH_MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject",
                        "-A", "--author-email", "--match-head-commit"}


def _cwd():
    return _CWD if (_CWD and os.path.isdir(_CWD)) else None


def _gh_merge_target(args: str):
    """Get (selector, repo from -R) from the gh pr merge arguments."""
    try:
        toks = shlex.split(args)
    except ValueError:
        return None, None
    sel, repo, i = None, None, 0
    while i < len(toks):
        t = toks[i]
        if t in GH_MERGE_VALUE_FLAGS:
            if t in ("-R", "--repo") and i + 1 < len(toks):
                repo = toks[i + 1]
            i += 2
            continue
        if t.startswith("--repo="):
            repo = t.split("=", 1)[1]
        elif not t.startswith("-") and sel is None:
            sel = t
        i += 1
    if not repo and sel:
        u = re.match(r"^https?://([^/]+)/([^/]+)/([^/]+)/pull/\d+", sel)
        if u:
            repo = "/".join(u.groups())  # a URL selector points at that repo
    return sel, repo


def _gh_base(cwd, sel, repo):
    """Look up the PR's merge-target branch with gh pr view. None if unavailable."""
    cmd = ["gh", "pr", "view"] + ([sel] if sel else []) + (["-R", repo] if repo else []) \
        + ["--json", "baseRefName", "-q", ".baseRefName"]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return None
    name = r.stdout.strip()
    return name if r.returncode == 0 and name and "\n" not in name else None


def rule_post_merge_pull(command: str):
    m = MERGE_RE.search(command)
    if not m:
        return None
    cwd = _cwd()
    if cwd is None:
        return None
    try:
        g = GH_MERGE_RE.search(command)
        if g:
            sel, repo = _gh_merge_target(g.group(1))
            if repo and not _same_repo(cwd, repo):
                return None  # only merged a PR in another repo
            base = _gh_base(cwd, sel, repo) or _default_branch(cwd)
        else:
            base = _default_branch(cwd)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return _pull_branch(base)


def _merge_sha(resp):
    """Find the merge commit SHA in the connector result (also opens nested JSON strings)."""
    if isinstance(resp, str):
        t = resp.strip()
        if t[:1] in "{[":
            try:
                return _merge_sha(json.loads(t))
            except ValueError:
                return None
        return None
    if isinstance(resp, dict):
        v = resp.get("sha")
        if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{40}", v):
            return v
        resp = list(resp.values())
    if isinstance(resp, list):
        for v in resp:
            found = _merge_sha(v)
            if found:
                return found
    return None


def rule_post_merge_pull_mcp(tool_input: dict):
    """After a connector merge. Catch up only when the cwd is the same repo and the local branch is the merge target."""
    owner, repo = tool_input.get("owner"), tool_input.get("repo")
    cwd = _cwd()
    if not (owner and repo and cwd):
        return None
    try:
        if _origin_slug(cwd) != f"{owner}/{repo}".lower():
            return None
        sha = _merge_sha(_RESPONSE)
        if not sha:
            return _pull_branch(_default_branch(cwd))
        branch = _current_branch(cwd)
        if not branch or branch == "HEAD":
            return None
        _git(["fetch", "--quiet", "origin", "--", branch], cwd)
        if _git(["merge-base", "--is-ancestor", sha, f"origin/{branch}"], cwd).returncode != 0:
            return None  # the merge target is not the local branch
    except (subprocess.TimeoutExpired, OSError):
        return None
    return _pull_branch(branch)


def _pull_branch(base):
    """If base is checked out locally and behind origin/base, catch up with --ff-only."""
    cwd = _cwd()
    if cwd is None or not base:
        return None
    try:
        if _current_branch(cwd) != base:
            return None  # don't pull origin/<base> into a branch other than the merge target
        state = _repo_state(cwd, base)
        if state is None:
            return inject(
                f"[git-freshness] Could not compare with origin/{base}, so it is unknown whether local {base} is up to date"
                " (offline, expired auth, branch missing on the remote, etc.)."
                f" If needed, catch up with `git pull --ff-only origin {base}`."
            )
        behind, dirty = state
        if behind == 0:
            return None  # already up to date = silent
        # --ff-only refuses on its own if conflicting local changes exist (never breaks anything behind your back).
        # Never auto-stash: a conflicting stash pop silently wrecks work.
        r = _git(["pull", "--ff-only", "origin", base], cwd, timeout=60)
        if r.returncode == 0:
            return inject(
                f"[git-freshness] Auto-pulled local {base} (caught up {behind} commits)."
                " Any job that runs this checkout directly now runs the merged code."
            )
        detail = (r.stderr or r.stdout).strip().splitlines()
        detail = detail[-1] if detail else "(reason unknown)"
        files = ", ".join(l[3:] for l in dirty[:5]) or "(none)"
        return inject(
            f"[git-freshness] ⚠️ Local {base} is {behind} commits behind origin/{base},"
            f" but the automatic pull failed: {detail}\n"
            f"{len(dirty)} uncommitted change(s): {files}\n"
            "**Nothing was stashed automatically** (to avoid wrecking work with a conflicting stash pop)."
            " Ask the user whether to commit or stash the changes."
            " Until it is pulled, this checkout keeps the old code."
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


RULES = [rule_post_merge_pull]          # rules that look at the Bash command
MCP_RULES = {"merge_pull_request": rule_post_merge_pull_mcp}  # connector tool name (suffix) -> rule


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name") or ""
    global _CWD, _RESPONSE
    _CWD = data.get("cwd") or os.getcwd()
    _RESPONSE = data.get("tool_response")
    if tool.startswith("mcp__"):
        rule = MCP_RULES.get(tool.rsplit("__", 1)[-1])
        result = rule(data.get("tool_input") or {}) if rule else None
        if result:
            print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    if tool != "Bash":
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "")
    for rule in RULES:
        result = rule(command)
        if result:
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
