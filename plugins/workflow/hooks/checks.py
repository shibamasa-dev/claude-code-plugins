#!/usr/bin/env python3
"""pr-checks: at PR creation, check that the repo's check command passed locally on the tree being proposed.

  checks.py run                 run the repo's check command and, when it exits 0, record a pass for the tree
  checks.py run --working-tree  run the working tree's command instead (to try a new config); never records
  checks.py report [--all]      list the PR creations that had no recorded pass

The command is `prChecks` in `.claude/verification.json` on origin's default branch (read like commit_gate.py reads
it: through the local origin/HEAD, so a branch cannot change the command it is judged by; without an origin remote the
working tree is read). The tree is identified by commit_gate.fingerprint(): the working tree's change against
merge-base(HEAD, origin/HEAD), untracked files included. `run` fingerprints before and after the command and records
only when both are equal, so a command that edits the tree (a formatter, an untracked output) records nothing.

Passes live in the repo: <git common dir>/workflow-pr-checks.json ({fingerprint: {at, command}}, newest 50), shared
by worktrees and sessions (the same tree gives the same result). They are not under CLAUDE_PLUGIN_DATA because `run`
is started from Bash, where that variable is not this plugin's; the git common dir is the one place both `run` and
the hook can derive.

The gate itself is pr_gate(), called by dev_flow_gate.py after its own PR-body check passed.
Modes (`off` / `observe` / `enforce`): `prChecksGate` in the repo file, else userConfig `pr_checks_gate`, else off.
  off      pr_gate() reads the repo's config (two to four local git calls per PR creation) and returns. Nothing is
           written, said or denied.
  observe  never blocks; logs one line per PR creation ({ts, pr_head, fingerprint, had_pass, ...}) and says so when
           there is no pass.
  enforce  denies a PR creation with no recorded pass for the tree, unless the body has
           `Local-Checks: none — <reason>` (logged as explained). After two denials in a session the next one is let
           through (logged as released).
It denies only when it is certain which tree the PR proposes: the PR's repo is the origin of the directory it is
created from and its head is the branch checked out there. Anything else (directory unknown, another repo or head,
default branch unknown, no `prChecks` command, fingerprint unavailable) is said and logged, never denied.
Log: <CLAUDE_PLUGIN_DATA or ~/.claude/state>/checks/log.jsonl (written by the hook only).
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import commit_gate as cg  # noqa: E402  (repo, default-branch config, fingerprint and locked files are item 3's)

TAG = "[pr-checks]"
PASS_FILE = "workflow-pr-checks.json"
KEEP = 50
RELEASE_AFTER = 2
# Within a line only [ \t], so an empty reason cannot borrow the next line
EXPLAIN_RE = re.compile(r"^[ \t]*Local-Checks:[ \t]*none[ \t]*[—–-]+[ \t]*\S", re.I | re.M)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
ORIGIN_RE = re.compile(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$")


def state_dir():
    return os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/.claude/state"), "checks")


def log(entry):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(os.path.join(state_dir(), "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": cg.now(), **entry}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def user_mode():
    return cg.norm_mode(os.environ.get("CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE"))


def settings(top):
    """{"mode", "command", "source", "invalid"}. The repo file on the default branch wins over userConfig."""
    cfg, source = cg.repo_config(top)
    repo_mode = cfg.get("prChecksGate")
    valid = isinstance(repo_mode, str) and repo_mode.strip().lower() in cg.MODES
    mode = cg.norm_mode(repo_mode) if valid else user_mode()  # an unreadable repo value does not switch the gate off
    if source == "unknown":
        mode = "off" if user_mode() == "off" else "unknown"
    command = cfg.get("prChecks")
    command = command.strip() if isinstance(command, str) and command.strip() else None
    return {"mode": mode, "command": command, "source": source,
            "invalid": None if repo_mode is None or valid else repo_mode}


# ------------------------------------------------------------------ passes
def command_key(command):
    return hashlib.sha1(command.encode()).hexdigest()[:12]


def pass_path(common):
    return os.path.join(common, PASS_FILE)


def has_pass(common, fp, command):
    """Whether this tree passed this command (a pass under an older command does not count)."""
    try:
        with open(pass_path(common), encoding="utf-8") as f:
            ent = (json.load(f).get("passes") or {}).get(fp)
    except Exception:
        return False
    return isinstance(ent, dict) and ent.get("command") == command_key(command)


def record_pass(common, fp, command):
    with cg.Locked(pass_path(common), {"passes": {}}) as d:
        passes = d.setdefault("passes", {})
        passes[fp] = {"at": cg.now(), "command": command_key(command)}
        d["passes"] = dict(sorted(passes.items(), key=lambda kv: kv[1].get("at", ""))[-KEEP:])


# ------------------------------------------------------------------ the gate (called by dev_flow_gate.py)
def origin_repo(top):
    rc, url = cg.git(top, "remote", "get-url", "origin")
    m = ORIGIN_RE.search(url) if rc == 0 else None
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def uncertain(top, where, repo, head):
    """Why the tree at top may not be what the PR proposes; None when it certainly is."""
    origin = origin_repo(top) if repo or (head and ":" in head) else None
    if repo and repo.lower() != (origin or ""):
        return "the PR goes to a repo that is not this directory's origin"
    branch = cg.branch_of(top)
    if not branch or branch == "HEAD":
        return "no branch is checked out"
    owner, _, name = (head or "").rpartition(":")  # --head owner:branch names a branch of that owner's fork
    if owner and owner.lower() != (origin or "/").split("/")[0]:
        return "the PR's head is in a repo that is not this directory's origin"
    if head and name != branch:
        return "the PR's head is not the branch checked out here"
    return None


def pr_gate(inp, where, repo, head, body):
    """("deny", reason) | ("note", text) | None.
    where: the directory the PR is created from (None when it cannot be told from the command).
    repo: the owner/name the call names (gh -R, GH_REPO, the connector's owner and repo); None when gh takes origin.
    head: the head the call names; None when gh takes the checked-out branch."""
    sid = inp["session_id"]
    top, common = cg.repo_of(where) if where else (None, None)
    if not top:
        # Not judged against the session's directory. Said only where the gate is on there (or in userConfig)
        stop, _ = cg.repo_of(inp.get("cwd"))
        mode = settings(stop)["mode"] if stop else user_mode()
        if mode in ("off", "unknown"):
            return None
        log({"session": sid, "repo": stop, "mode": mode, "decision": "unresolved",
             "why": "directory unknown" if not where else "not a git work tree"})
        return "note", (f"{TAG} cannot tell which repo this PR is created from, so local checks were not looked up. "
                        "Create it from the repo's directory (`cd <path> && gh pr create ...`).")
    s = settings(top)
    mode = s["mode"]
    if mode == "off":
        return None
    entry = {"session": sid, "repo": top, "branch": cg.branch_of(top), "mode": mode}
    if mode == "unknown":
        log({**entry, "decision": "nogate"})
        return "note", (f"{TAG} cannot tell origin's default branch (no local origin/HEAD), so the repo's {cg.CONFIG} "
                        "cannot be read: not gating. `git remote set-head origin --auto` fixes it.")
    notes = []
    if s["source"] == "working-tree":
        notes.append(f"{TAG} no origin remote: {cg.CONFIG} is read from the working tree.")
    if s["invalid"] is not None:
        log({**entry, "decision": "config_invalid", "value": repr(s["invalid"])[:100]})
        notes.append(f"{TAG} prChecksGate in the default branch's {cg.CONFIG} is {s['invalid']!r}, not one of "
                     f"{', '.join(cg.MODES)}: ignored, using userConfig ({mode}).")

    def note(text):
        return "note", "\n".join(notes + [text])

    if not s["command"]:
        log({**entry, "decision": "nocommand"})
        return note(f"{TAG} the gate is on ({mode}) but the default branch's {cg.CONFIG} has no `prChecks` command: "
                    "nothing to look up.")
    why = uncertain(top, where, repo, head)
    if why:
        log({**entry, "decision": "unresolved", "why": why})
        return note(f"{TAG} {why}, so local checks were not looked up.")
    fp = cg.fingerprint(top)
    if fp is None:
        log({**entry, "decision": "unchecked"})
        return note(f"{TAG} could not fingerprint the tree in time: local checks were not looked up.")
    had = has_pass(common, fp, s["command"])
    _, pr_head = cg.git(top, "rev-parse", "--verify", "--quiet", "HEAD")
    rc, status = cg.git(top, "status", "--porcelain")
    entry.update(pr_head=pr_head, fingerprint=fp, had_pass=had, dirty=bool(status) if rc == 0 else None)
    counter = os.path.join(state_dir(), "blocks", re.sub(r"[^\w.-]", "_", sid) + ".json")
    key = cg.repo_key(common)
    explained = bool(EXPLAIN_RE.search(HTML_COMMENT_RE.sub("", body or "")))
    if had or explained:
        if os.path.exists(counter):
            with cg.Locked(counter, {}) as c:
                c.pop(key, None)
        log({**entry, "decision": "allow" if had else "explained"})
        return ("note", "\n".join(notes)) if notes else None
    runner = f"python3 {shlex.quote(os.path.abspath(__file__))} run"  # the plugin may live under a path with spaces
    # The whole command is shown (never a prefix that could hide its tail): `run` executes it through the shell
    shown = s["command"] if len(s["command"]) <= 400 else (
        f"{len(s['command'])} characters: read prChecks in {cg.CONFIG} on the default branch before running it")
    problem = (f"no recorded pass of the repo's checks (`{shown}`) for this tree. Run `{runner}` in the "
               "repo and create the PR again, or add `Local-Checks: none — <reason>` to the PR body")
    if mode == "observe":
        log({**entry, "decision": "would_block"})
        return note(f"{TAG} observe: this PR would be blocked: {problem}.")
    with cg.Locked(counter, {}) as c:
        n = c.get(key, 0)
        released = n >= RELEASE_AFTER
        if released:
            c.pop(key, None)
        else:
            c[key] = n + 1
    if released:
        log({**entry, "decision": "released"})
        return note(f"{TAG} let through after {RELEASE_AFTER} blocks in this session (logged as released): {problem}.")
    log({**entry, "decision": "would_block"})
    return "deny", (f"{TAG} PR blocked ({n + 1}/{RELEASE_AFTER}; after {RELEASE_AFTER} blocks in a session the next "
                    f"one is let through): {problem}.")


# ------------------------------------------------------------------ CLI
def run(argv):
    working = "--working-tree" in argv
    top, common = cg.repo_of(os.getcwd())
    if not top:
        print(f"{TAG} not inside a git work tree.", file=sys.stderr)
        return 2
    if working:
        try:
            with open(os.path.join(top, cg.CONFIG), encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
        command = cfg.get("prChecks") if isinstance(cfg, dict) else None
        command = command.strip() if isinstance(command, str) and command.strip() else None
        where = f"the working tree's {cg.CONFIG}"
    else:
        s = settings(top)
        if s["source"] == "unknown":
            print(f"{TAG} cannot tell origin's default branch (no local origin/HEAD). "
                  "`git remote set-head origin --auto` fixes it.", file=sys.stderr)
            return 2
        command = s["command"]
        where = f"{cg.CONFIG} on " + ("the default branch" if s["source"] == "default-branch" else "the working tree")
    if not command:
        print(f"{TAG} no `prChecks` command in {where}.", file=sys.stderr)
        return 2
    before = None if working else cg.fingerprint(top)
    print(f"{TAG} running (from {where}): {command}", flush=True)
    rc = subprocess.run(command, shell=True, cwd=top).returncode
    if rc != 0:
        print(f"{TAG} failed (exit {rc}): nothing recorded.", file=sys.stderr)
        return rc if 0 < rc < 126 else 1
    if working:
        print(f"{TAG} passed. Not recorded (--working-tree never records).")
        return 0
    after = cg.fingerprint(top)
    if before is None or after is None:
        print(f"{TAG} passed, but the tree could not be fingerprinted: nothing recorded.", file=sys.stderr)
        return 3
    if before != after:
        print(f"{TAG} passed, but the tree changed during the run (a formatter, or an output file that is not "
              "ignored): nothing recorded. Run it again once the tree is stable.", file=sys.stderr)
        return 3
    try:
        record_pass(common, after, command)
    except OSError as e:
        print(f"{TAG} passed, but the pass could not be written ({e}): nothing recorded.", file=sys.stderr)
        return 3
    print(f"{TAG} passed: recorded for {after}.")
    return 0


def report(all_rows=False):
    try:
        with open(os.path.join(state_dir(), "log.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except OSError:
        print("No pr-checks log yet.")
        return 0
    for r in rows:
        if all_rows or r.get("decision") in ("would_block", "released", "explained"):
            print(f"{r.get('ts')} {r.get('mode')} {r.get('decision')} {r.get('repo')} branch={r.get('branch')} "
                  f"head={(r.get('pr_head') or '')[:12]} fingerprint={r.get('fingerprint')} dirty={r.get('dirty')}")
    return 0


def main():
    if sys.argv[1:2] == ["run"]:
        return run(sys.argv[2:])
    if sys.argv[1:2] == ["report"]:
        return report("--all" in sys.argv[2:])
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
