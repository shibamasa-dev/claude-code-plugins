#!/usr/bin/env python3
"""full-test-gate: nudge for the full test suite by "how much changed since last time", and gate releases on it.

Applies only to projects whose default branch has .claude/full-test.json at the repository root (does nothing otherwise).
The file is read from origin/<default branch>, not from the working tree, so a branch cannot change the rule it is judged by:
a new or changed config takes effect once it is merged. Without an origin remote the working tree is read (with a note on stderr).
When origin's default branch cannot be told (no local origin/HEAD and origin does not answer), it neither gates nor records.

  {
    "command": "cd etl/database/stored_procedures && python -m pytest tests/ -q",  # full test suite (run from the repository root)
    "paths": ["etl/database"],            # paths whose changes are counted
    "base": "origin/main",                # defaults to origin's default branch (see default_branch)
    "thresholds": {"lines": 500, "commits": 10, "days": 14},   # notify when any of these is exceeded
    "skipped_regex": "(\\d+) skipped",   # picks the skip count out of the output (optional)
    "max_skipped": 20,                    # do not record if the skip count exceeds this (optional)
    "gate": ["build-release\\.sh"]        # block these commands if the target paths changed since the last full run
  }

Usage (python3 "<plugin root>/hooks/full-test-gate.py" <subcommand>; the hook messages print the full path):
  full-test-gate.py run      Run the full test suite and record it if it passes. It records only when
                             "the target paths have the same content as base" (results from a work branch are not recorded).
  full-test-gate.py run --working-tree
                             Run the working tree's config (to try a new one before merging it). Never records
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


# Git variables that select a repository are dropped, so `git -C <repo>` reads that repo and not one named by the environment
_REPO_SELECT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")
GIT_ENV = {**{k: v for k, v in os.environ.items() if k not in _REPO_SELECT_VARS}, "GIT_TERMINAL_PROMPT": "0"}
MISS_FILE = "full-test-gate-origin-miss"  # in the git common dir; its mtime is the last failed network attempt
NO_BASE = "no comparison base (origin's default branch is unknown and the config has no \"base\")"
MISS_TTL = 3600                           # seconds before origin is tried again after a failure


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=20, env=GIT_ENV,
                       stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout.strip()


CONFIG = ".claude/full-test.json"


def read_config(top, working_tree=False):
    """The config text, read from the default branch (origin/<default>) so a branch cannot change the command that records
    a pass or drop the gate that blocks its own release. None when the file is not there (= not opted in; never falls back
    to the working tree). Without an origin remote no PR can exist, so the working tree is read and stderr says so.
    working_tree=True (`run --working-tree`) reads the working tree on purpose."""
    no_origin = not working_tree and git(top, "remote", "get-url", "origin")[0] != 0
    if working_tree or no_origin:
        try:
            with open(os.path.join(top, CONFIG)) as f:
                text = f.read()
        except OSError:
            return None
        if no_origin:
            print(f"[full-test-gate] no origin remote: reading {CONFIG} from the working tree", file=sys.stderr)
        return text
    base = default_branch(top)
    if base is None:
        print("[full-test-gate] cannot tell origin's default branch (no local origin/HEAD, origin unreachable or its "
              "ref unavailable; retried after 1 hour): not gating", file=sys.stderr)
        return None
    rc, text = git(top, "show", f"refs/remotes/{base}:{CONFIG}")
    return text if rc == 0 else None


def load_project(cwd, working_tree=False):
    """(config, toplevel, state_path). (None, None, None) when the project is not opted in."""
    rc, top = git(cwd, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None, None, None
    try:
        cfg = json.loads(read_config(top, working_tree))
    except Exception:
        return None, None, None
    _, common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    key = hashlib.sha1(common.encode()).hexdigest()[:16]
    return cfg, top, os.path.join(STATE_DIR, key + ".json")


def _miss_path(top):
    _, common = git(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.join(common, MISS_FILE)


def _net_allowed(top):
    """False within MISS_TTL of a failed network attempt, so a hook that runs on every Bash call does not wait each time."""
    try:
        return time.time() - os.path.getmtime(_miss_path(top)) >= MISS_TTL
    except OSError:
        return True


def _mark_miss(top):
    try:
        with open(_miss_path(top), "a"):
            pass
        os.utime(_miss_path(top))
    except OSError:
        pass


def _net(top, *args):
    """A network git command (5 s, no prompt). (returncode, stdout); a failure is remembered for MISS_TTL."""
    try:
        r = subprocess.run(["git", "-C", top, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=5, env=GIT_ENV)
        rc, out = r.returncode, r.stdout
    except (subprocess.TimeoutExpired, OSError):
        rc, out = 1, ""
    if rc != 0:
        _mark_miss(top)
    return rc, out


def _has_ref(top, name):
    return git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}")[0] == 0


_DEFAULT = {}


def default_branch(top):
    """`origin/<name>` for origin's default branch, or None when it cannot be told. One answer serves both the config
    source and the comparison base. Order: the local origin/HEAD when the ref it names exists locally (no network; a stale
    one is fine); else ask origin once (ls-remote) and cache a success as the local origin/HEAD; a failure is cached for
    MISS_TTL. A dangling origin/HEAD (its ref was pruned) is not fetched by name, since that name may now be any pushed branch. origin/main or origin/master is never guessed,
    since a pushed branch that is not the default would then supply the config. A missing origin/<name> is fetched once
    into that ref. None without an origin remote."""
    if top in _DEFAULT:
        return _DEFAULT[top]
    name = None
    rc, ref = git(top, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and ref.startswith("origin/") and _has_ref(top, ref[len("origin/"):]):
        name = ref[len("origin/"):]
    elif git(top, "remote", "get-url", "origin")[0] == 0 and _net_allowed(top):
        rc, out = _net(top, "ls-remote", "--symref", "origin", "HEAD")
        m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", out, re.M) if rc == 0 else None
        if m:
            name = m.group(1)
            git(top, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{name}")
        elif rc == 0:
            _mark_miss(top)  # answered without a HEAD symref: treat as unknown for MISS_TTL too
    if name and not _has_ref(top, name) and _net_allowed(top):
        # An explicit destination, so a single-branch clone (whose refspec does not cover name) still gets origin/<name>
        _net(top, "fetch", "--quiet", "origin", "--", f"+refs/heads/{name}:refs/remotes/origin/{name}")
    _DEFAULT[top] = f"origin/{name}" if name and _has_ref(top, name) else None
    return _DEFAULT[top]


def base_of(top, cfg):
    """The comparison base: the config's base, else origin's default branch. None when neither is known."""
    return cfg.get("base") or default_branch(top)


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
        print(f"Not configured (no {CONFIG} on the default branch)"); return 0
    state = load_state(sp)
    if not state:
        print(f"No full test run recorded. Run: {SELF} run"); return 0
    if base_of(top, cfg) is None:
        print(f"Cannot compare: {NO_BASE}"); return 1
    m = measure(top, cfg, state["sha"], base_of(top, cfg))
    if m is None:
        print(f"Cannot compare ({base_of(top, cfg)} or the recorded {state['sha'][:8]} is not available locally). Run git fetch and try again")
        return 1
    text, _ = describe(state, m)
    print(text + f" (skipped {state.get('skipped')})")
    return 0


def cmd_run(cwd, working_tree=False):
    cfg, top, sp = load_project(cwd, working_tree)
    if not cfg:
        print(f"Not configured (no {CONFIG} on the default branch)"); return 1
    base, paths = base_of(top, cfg), cfg.get("paths") or ["."]
    rc_same = 0
    if not working_tree and base is None:
        print(f"[full-test-gate] {NO_BASE}. Not run, not recorded"); return 1
    if not working_tree:  # --working-tree never records, so it needs no comparison base
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
    if working_tree:
        print(f"[full-test-gate] Passed with the working tree's {CONFIG}. Not recorded (--working-tree never records; "
              "the config takes effect once it is merged to the default branch)")
        return 0
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
    if base_of(top, cfg) is None:
        return  # nothing to compare with (no origin and no "base" in the config)
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
    reason += f" First pass `{SELF} run` while in the same state as {base_of(top, cfg) or 'the comparison base'}."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": "[full-test] " + reason}},
                     ensure_ascii=False))


def main():
    if len(sys.argv) > 1:
        if sys.argv[1:] == ["run", "--working-tree"]:
            return cmd_run(os.getcwd(), working_tree=True)
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
