#!/usr/bin/env python3
"""full-test-gate: nudge for the full test suite by "how much changed since last time", and gate releases on it.

Applies only to projects that put .claude/full-test.json at the repository root (does nothing otherwise).

  {
    "command": "cd etl/database/stored_procedures && python -m pytest tests/ -q",  # full test suite (run from the repository root)
    "paths": ["etl/database"],            # paths whose changes are counted
    "base": "origin/main",                # defaults to the repo's default branch (asks origin; if unreachable, origin/HEAD; if missing, origin/main)
    "thresholds": {"lines": 500, "commits": 10, "days": 14},   # notify when any of these is exceeded
    "skipped_regex": "(\\d+) skipped",   # picks the skip count out of the output (optional)
    "max_skipped": 20,                    # do not record if the skip count exceeds this (optional)
    "gate": ["build-release\\.sh"]        # block these commands if the target paths changed since the last full run
  }

Usage (python3 "<plugin root>/hooks/full-test-gate.py" <subcommand>; the hook messages print the full path):
  full-test-gate.py run      Run the full test suite and record it if it passes. It records only when
                             "the target paths have the same content as base" (results from a work branch are not recorded).
  full-test-gate.py status   Show the last record and how much has changed since
As a hook (branches on hook_event_name from stdin):
  SessionStart         Print a one-line notice when a threshold is exceeded (does not block)
  PreToolUse(Bash)     Deny commands matching gate when there are unverified changes
State: $FULL_TEST_STATE_DIR (default ~/.claude/state/full-test)/<project-key>.json
       project-key = sha1 of the git common dir (shared across worktrees). Shape: {"sha", "at", "skipped"}
"""
import hashlib, json, os, re, subprocess, sys, time

STATE_DIR = os.path.expanduser(os.environ.get("FULL_TEST_STATE_DIR", "~/.claude/state/full-test"))
DEFAULT_THRESHOLDS = {"lines": 500, "commits": 10, "days": 14}
SELF = f'python3 "{os.path.abspath(__file__)}"'  # how messages tell Claude to run this script


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=20)
    return r.returncode, r.stdout.strip()


def load_project(cwd):
    """(config, toplevel, state_path). (None, None, None) when the project is not opted in."""
    rc, top = git(cwd, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None, None, None
    try:
        with open(os.path.join(top, ".claude", "full-test.json")) as f:
            cfg = json.load(f)
    except Exception:
        return None, None, None
    _, common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    key = hashlib.sha1(common.encode()).hexdigest()[:16]
    return cfg, top, os.path.join(STATE_DIR, key + ".json")


def _remote_default(top):
    """The default branch origin reports right now (ls-remote, read only). Asked first because the local origin/HEAD
    is not updated by fetch. None when unreachable or authentication is needed (never makes the user wait)."""
    try:
        r = subprocess.run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=top, capture_output=True, stdin=subprocess.DEVNULL,
                           text=True, timeout=5, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (subprocess.TimeoutExpired, OSError):
        return None
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", r.stdout, re.M) if r.returncode == 0 else None
    return m.group(1) if m else None


_DEFAULT_BASE = {}


def _has_remote_ref(top, name):
    """Whether origin/<name> exists locally. If not, fetch it once (False if that fails)."""
    if git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}")[0] == 0:
        return True
    try:
        subprocess.run(["git", "-C", top, "fetch", "--quiet", "origin", "--", name], capture_output=True, stdin=subprocess.DEVNULL,
                       timeout=5, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (subprocess.TimeoutExpired, OSError):
        return False
    return git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}")[0] == 0


def default_base(top):
    """The comparison base when the config has no base. Ask origin; if unreachable, the local origin/HEAD; if that is missing too,
    origin/main (or origin/master when origin/main is missing and origin/master exists).
    Within one hook run, reuse the first result (origin is asked only once)."""
    if top not in _DEFAULT_BASE:
        name = _remote_default(top)
        if name and _has_remote_ref(top, name):
            _DEFAULT_BASE[top] = f"origin/{name}"
        else:
            rc, ref = git(top, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
            if rc == 0 and ref.startswith("origin/"):
                _DEFAULT_BASE[top] = ref
            elif git(top, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main")[0] != 0 \
                    and git(top, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/master")[0] == 0:
                _DEFAULT_BASE[top] = "origin/master"
            else:
                _DEFAULT_BASE[top] = "origin/main"
    return _DEFAULT_BASE[top]


def base_of(top, cfg):
    return cfg.get("base") or default_base(top)


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def measure(top, cfg, sha, target):
    """How much the target paths changed from sha to target (a ref; None means the working tree). None if they cannot be compared (distinct from 0 changes)."""
    paths = cfg.get("paths") or ["."]
    rng = [sha, target] if target else [sha]
    rc, stat = git(top, "diff", "--shortstat", *rng, "--", *paths)
    if rc != 0:
        return None
    nums = {k: int(v) for v, k in re.findall(r"(\d+) (file|insertion|deletion)", stat)}
    commits = 0
    if target:
        rc, c = git(top, "rev-list", "--count", f"{sha}..{target}", "--", *paths)
        if rc != 0:
            return None
        commits = int(c or 0)
    return {"files": nums.get("file", 0),
            "lines": nums.get("insertion", 0) + nums.get("deletion", 0),
            "commits": commits}


def describe(state, m):
    days = int((time.time() - state["at"]) // 86400)
    return (f"Since the last full test run ({time.strftime('%Y-%m-%d', time.localtime(state['at']))}, {state['sha'][:8]}): "
            f"{m['lines']} lines / {m['files']} files / {m['commits']} commits / {days} days"), days


def cmd_status(cwd):
    cfg, top, sp = load_project(cwd)
    if not cfg:
        print("Not configured (no .claude/full-test.json)"); return 0
    state = load_state(sp)
    if not state:
        print(f"No full test run recorded. Run: {SELF} run"); return 0
    m = measure(top, cfg, state["sha"], base_of(top, cfg))
    if m is None:
        print(f"Cannot compare ({base_of(top, cfg)} or the recorded {state['sha'][:8]} is not available locally). Run git fetch and try again")
        return 1
    text, _ = describe(state, m)
    print(text + f" (skipped {state.get('skipped')})")
    return 0


def cmd_run(cwd):
    cfg, top, sp = load_project(cwd)
    if not cfg:
        print("Not configured (no .claude/full-test.json)"); return 1
    base, paths = base_of(top, cfg), cfg.get("paths") or ["."]
    rc_same, _ = git(top, "diff", "--quiet", base, "--", *paths)
    if rc_same > 1:
        print(f"[full-test-gate] Cannot read the comparison base {base} (not available locally). Run git fetch and try again"); return 1
    p = subprocess.Popen(cfg["command"], shell=True, cwd=top, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    out = []
    for line in p.stdout:
        sys.stdout.write(line); out.append(line)
    if p.wait() != 0:
        print(f"[full-test-gate] Failed (exit {p.returncode}). Not recorded"); return p.returncode
    skipped = None
    if cfg.get("skipped_regex"):
        found = re.findall(cfg["skipped_regex"], "".join(out))
        skipped = int(found[-1]) if found else 0
    if skipped is not None and cfg.get("max_skipped") is not None and skipped > cfg["max_skipped"]:
        print(f"[full-test-gate] {skipped} skipped > limit {cfg['max_skipped']}. Not recorded (check preconditions such as real sample data)")
        return 1
    if rc_same != 0:
        print(f"[full-test-gate] Passed, but not recorded because the target paths differ from {base} (this is a result of work in progress)")
        return 0
    _, sha = git(top, "rev-parse", base)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(sp, "w") as f:
        json.dump({"sha": sha, "at": time.time(), "skipped": skipped}, f)
    print(f"[full-test-gate] Recorded: {base} {sha[:8]} (skipped {skipped})")
    return 0


def hook_session_start(cwd):
    cfg, top, sp = load_project(cwd)
    if not cfg:
        return
    state = load_state(sp)
    if not state:
        print(f"[full-test] No full test run is recorded. Run `{SELF} run` once while in the same state as "
              f"{base_of(top, cfg)}; after that you will be notified by how much has changed.")
        return
    m = measure(top, cfg, state["sha"], base_of(top, cfg))
    if m is None:
        print(f"[full-test] Could not compare the last full test run ({state['sha'][:8]}) with {base_of(top, cfg)}. "
              "Run git fetch and you will be notified by how much has changed from next time.")
        return
    text, days = describe(state, m)
    th = {**DEFAULT_THRESHOLDS, **(cfg.get("thresholds") or {})}
    over = [k for k, v in (("lines", m["lines"]), ("commits", m["commits"])) if v >= th[k]]
    if m["lines"] and days >= th["days"]:
        over.append("days")
    if over:
        print(f"[full-test] Time for a full test run. {text} (thresholds exceeded: {', '.join(over)}). "
              f"At a break in your work, run `{SELF} run` while in the same state as {base_of(top, cfg)}.")


def hook_pre_bash(cwd, command):
    cfg, top, sp = load_project(cwd)
    if not cfg or not any(re.search(g, command) for g in cfg.get("gate") or []):
        return
    state = load_state(sp)
    if state:
        m = measure(top, cfg, state["sha"], None)
        if m is None or m["lines"] == 0:
            return  # do not block when it cannot be compared (as before)
        reason = (f"There are changes not covered by a full test run ({m['lines']} lines / "
                  f"{m['files']} files in the target paths since {state['sha'][:8]}).")
    else:
        reason = "No full test run is recorded."
    reason += f" First pass `{SELF} run` while in the same state as {base_of(top, cfg)}."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": "[full-test] " + reason}},
                     ensure_ascii=False))


def main():
    if len(sys.argv) > 1:
        return {"run": cmd_run, "status": cmd_status}[sys.argv[1]](os.getcwd())
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cwd = data.get("cwd") or os.getcwd()
    try:
        if data.get("hook_event_name") == "SessionStart":
            hook_session_start(cwd)
        elif data.get("hook_event_name") == "PreToolUse" and data.get("tool_name") == "Bash":
            hook_pre_bash(cwd, (data.get("tool_input") or {}).get("command", ""))
    except Exception:
        pass  # a hook never stops the work
    return 0


if __name__ == "__main__":
    sys.exit(main())
