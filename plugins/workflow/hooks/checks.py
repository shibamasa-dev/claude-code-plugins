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
by worktrees and sessions (the same tree gives the same result); the log is next to it
(workflow-pr-checks.log.jsonl). They are not under CLAUDE_PLUGIN_DATA because `run` and `report` are started from
Bash, where that variable is not this plugin's; the git common dir is the one place both the CLI and the hook can
derive. Only the per-session denial count, which the hook alone reads and writes, is in
<CLAUDE_PLUGIN_DATA or ~/.claude/state>/checks/blocks/.

An untracked file that the `gh pr create` call itself names as its body (`--body-file` / `-F`) is left out of the
fingerprint, so writing the PR body inside the repo after the checks ran does not undo the pass. For a body file that
was already there when the checks ran, `run` also records, for each untracked file (up to 10), the fingerprint with
that one file left out, so editing the body afterwards does not undo the pass either. Any other new, changed or
deleted untracked file that is not ignored counts as a change.
A recorded pass is trusted as it is: the gate looks it up and never runs the checks itself.

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
default branch unknown, no `prChecks` command, fingerprint unavailable, a git command earlier in the same Bash call
that may move the branch or the tree, `gh repo set-default` naming another remote, an error while deciding) is said
and logged, never denied. When the log cannot be written, the note is still given.
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
LOG_FILE = "workflow-pr-checks.log.jsonl"
KEEP = 50
MAX_WITHOUT = 10   # untracked files for which `run` records a fingerprint with that one file left out
RELEASE_AFTER = 2
# Within a line only [ \t], so an empty reason cannot borrow the next line
EXPLAIN_RE = re.compile(r"^[ \t]*Local-Checks:[ \t]*none[ \t]*[—–-]+[ \t]*\S", re.I | re.M)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
ORIGIN_RE = re.compile(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$")


def state_dir():
    """Where the per-session denial count lives (read and written by the hook only)."""
    return os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/.claude/state"), "checks")


_log_failed = []  # set when a log line could not be written, so pr_gate() can say so


def log(common, entry):
    """One line in <git common dir>/workflow-pr-checks.log.jsonl (common is None when no repo is known)."""
    try:
        with open(os.path.join(common, LOG_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": cg.now(), **entry}, ensure_ascii=False) + "\n")
    except (OSError, TypeError):
        _log_failed.append(True)


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


def pass_without(common, rels, fp, command):
    """Whether a pass was recorded on a tree that, with one of the files in rels left out, was this one (the PR body
    file was there when the checks ran and may have been edited since)."""
    try:
        with open(pass_path(common), encoding="utf-8") as f:
            passes = json.load(f).get("passes") or {}
    except Exception:
        return False
    key = command_key(command)
    return any(isinstance(e, dict) and e.get("command") == key and isinstance(e.get("without"), dict)
               and any(e["without"].get(r) == fp for r in rels) for e in passes.values())


def untracked(top):
    """Untracked files that are not ignored, relative to top, as git spells them."""
    rc, out = cg.git(top, "ls-files", "--others", "--exclude-standard", "-z")
    return [p for p in out.split("\0") if p] if rc == 0 else []


def record_pass(common, fp, command, without=None):
    with cg.Locked(pass_path(common), {"passes": {}}) as d:
        passes = d.setdefault("passes", {})
        passes[fp] = {"at": cg.now(), "command": command_key(command), "without": without or {}}
        d["passes"] = dict(sorted(passes.items(), key=lambda kv: kv[1].get("at", ""))[-KEEP:])


# ------------------------------------------------------------------ the gate (called by dev_flow_gate.py)
def origin_repo(top):
    rc, url = cg.git(top, "remote", "get-url", "origin")
    m = ORIGIN_RE.search(url) if rc == 0 else None
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


# git subcommands that leave HEAD and the working tree as they are (anything else before `gh pr create` in the same
# Bash call may change what the PR proposes after this check has read it)
_GIT_KEEPS_TREE = {"push", "fetch", "status", "log", "diff", "show", "rev-parse", "remote", "add", "config",
                   "ls-files", "ls-remote", "describe", "branch", "tag", "merge-base", "cat-file", "blame", "shortlog"}
# gh calls that change neither the checkout nor gh's default repo (`gh pr checkout`, `gh repo set-default` do)
_GH_KEEPS_TREE = {("pr", "view"), ("pr", "list"), ("pr", "status"), ("pr", "checks"), ("pr", "diff"), ("repo", "view")}
_GH_KEEPS_TREE_GROUPS = {"issue", "api", "auth", "label", "run", "search", "workflow"}


def moved_before_create(command, cwd):
    """Whether a git or gh call that may change HEAD, the working tree or gh's default repo comes before
    `gh pr create` in this Bash command (`git switch b && gh pr create`, `gh pr checkout 5 && gh pr create`): the check
    would read the state as it is before the command runs."""
    for call in cg.commands(command, {"git", "gh"}, cwd):
        args = call["args"]
        if call["exe"] == "gh":
            if "pr" in args and "create" in args:
                return False
            pos = [a for a in args if not a.startswith("-")][:2]
            if not (pos[:1] and pos[0] in _GH_KEEPS_TREE_GROUPS) and tuple(pos) not in _GH_KEEPS_TREE:
                return True
            continue
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in cg._GIT_VALUE_OPTS else 1
        if i >= len(args) or args[i] not in _GIT_KEEPS_TREE:
            return True
    return False


def uncertain(inp, top, where, repo, head):
    """Why the tree at top may not be what the PR proposes; None when it certainly is."""
    if inp.get("tool_name") == "Bash" and moved_before_create((inp.get("tool_input") or {}).get("command", ""),
                                                              inp.get("cwd")):
        return ("an earlier git or gh command in the same call may change the branch, the tree or gh's default repo "
                "(run it in its own call, then create the PR)")
    if not repo:
        # gh takes the remote marked by `gh repo set-default` (git config remote.<name>.gh-resolved) before origin
        _, marked = cg.git(top, "config", "--get-regexp", r"^remote\..*\.gh-resolved$")
        # origin marked with anything but `base` (an owner/name: a repo other than the remote's own) is not origin either
        if any(line.split() != ["remote.origin.gh-resolved", "base"] for line in marked.splitlines() if line.strip()):
            return "gh's default repo (`gh repo set-default`) is not this directory's origin"
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


def body_exempt(top, body_file):
    """The untracked files in the repo that are the file this call names as its PR body, as git spells them (the
    name may differ in case on a case-insensitive filesystem; a symlink and its target are the same file). Empty when
    there is none, it is outside the repo, or it is tracked (a tracked file is part of what the PR proposes)."""
    if not body_file or not os.path.exists(body_file):
        return []
    out = []
    for p in untracked(top)[:5000]:
        try:
            if os.path.samefile(os.path.join(top, p), body_file):
                out.append(p)
        except OSError:
            pass
    return out


def pr_gate(inp, where, repo, head, body, body_file=None):
    """("deny", reason) | ("note", text) | None.
    where: the directory the PR is created from (None when it cannot be told from the command).
    repo: the owner/name the call names (gh -R, GH_REPO, the connector's owner and repo); None when gh takes origin.
    head: the head the call names; None when gh takes the checked-out branch.
    body_file: the file the call reads the PR body from (gh --body-file / -F), as an absolute path; None otherwise."""
    del _log_failed[:]
    try:
        res = _gate(inp, where, repo, head, body, body_file)
    except Exception as e:  # could not decide (also before the mode is known): said and logged, never silent or a denial
        try:
            _, common = cg.repo_of(where or inp.get("cwd"))
        except Exception:
            common = None
        log(common, {"session": inp.get("session_id"), "decision": "error", "error": f"{type(e).__name__}: {e}"[:200]})
        res = "note", f"{TAG} could not look up local checks ({type(e).__name__}): this PR was not checked."
    if _log_failed:  # only reached with the gate on (off never logs): the log line is lost, the note is not
        lost = f"{TAG} could not write its log ({LOG_FILE} in the git directory): this PR creation is not recorded."
        res = ("note", lost) if res is None else (res[0], res[1] + "\n" + lost)
    return res


def _gate(inp, where, repo, head, body, body_file):
    sid = inp["session_id"]
    top, common = cg.repo_of(where) if where else (None, None)
    if not top:
        # Not judged against the session's directory. Said only where the gate is on there (or in userConfig)
        stop, scommon = cg.repo_of(inp.get("cwd"))
        mode = settings(stop)["mode"] if stop else user_mode()
        if mode in ("off", "unknown"):
            return None
        log(scommon, {"session": sid, "repo": stop, "mode": mode, "decision": "unresolved",
                      "why": "directory unknown" if not where else "not a git work tree"})
        return "note", (f"{TAG} cannot tell which repo this PR is created from, so local checks were not looked up. "
                        "Create it from the repo's directory (`cd <path> && gh pr create ...`).")
    s = settings(top)
    if s["mode"] == "off":
        return None
    return _judge(inp, sid, top, common, s, where, repo, head, body, body_file)


def _judge(inp, sid, top, common, s, where, repo, head, body, body_file):
    mode = s["mode"]
    entry = {"session": sid, "repo": top, "branch": cg.branch_of(top), "mode": mode}
    if mode == "unknown":
        log(common, {**entry, "decision": "nogate"})
        return "note", (f"{TAG} cannot tell origin's default branch (no local origin/HEAD), so the repo's {cg.CONFIG} "
                        "cannot be read: not gating. `git remote set-head origin --auto` fixes it.")
    notes = []
    if s["source"] == "working-tree":
        notes.append(f"{TAG} no origin remote: {cg.CONFIG} is read from the working tree.")
    if s["invalid"] is not None:
        log(common, {**entry, "decision": "config_invalid", "value": repr(s["invalid"])[:100]})
        notes.append(f"{TAG} prChecksGate in the default branch's {cg.CONFIG} is {s['invalid']!r}, not one of "
                     f"{', '.join(cg.MODES)}: ignored, using userConfig ({mode}).")

    def note(text):
        return "note", "\n".join(notes + [text])

    if not s["command"]:
        log(common, {**entry, "decision": "nocommand"})
        return note(f"{TAG} the gate is on ({mode}) but the default branch's {cg.CONFIG} has no `prChecks` command: "
                    "nothing to look up.")
    why = uncertain(inp, top, where, repo, head)
    if why:
        log(common, {**entry, "decision": "unresolved", "why": why})
        return note(f"{TAG} {why}, so local checks were not looked up.")
    exempt = body_exempt(top, body_file)
    fp = cg.fingerprint(top, exclude=exempt)
    if fp is None:
        log(common, {**entry, "decision": "unchecked"})
        return note(f"{TAG} could not fingerprint the tree in time: local checks were not looked up.")
    # The body file was written after the checks ran (the tree without it has a pass), or it was already there and may
    # have been edited since (`run` recorded the tree with that one file left out)
    had = has_pass(common, fp, s["command"]) or (bool(exempt) and pass_without(common, exempt, fp, s["command"]))
    if not had and exempt:  # there and untouched, on a run that recorded no per-file fingerprints (over MAX_WITHOUT)
        with_body = cg.fingerprint(top)
        had = with_body is not None and has_pass(common, with_body, s["command"])
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
        log(common, {**entry, "decision": "allow" if had else "explained"})
        return ("note", "\n".join(notes)) if notes else None
    runner = f"python3 {shlex.quote(os.path.abspath(__file__))} run"  # the plugin may live under a path with spaces
    # The whole command is shown (never a prefix that could hide its tail): `run` executes it through the shell
    shown = s["command"] if len(s["command"]) <= 400 else (
        f"{len(s['command'])} characters: read prChecks in {cg.CONFIG} on the default branch before running it")
    problem = (f"no recorded pass of the repo's checks (`{shown}`) for this tree. Run `{runner}` in the "
               "repo and create the PR again, or add `Local-Checks: none — <reason>` to the PR body. Any edit "
               "since the last run undoes its pass, and new untracked files count: ignore them or re-run the checks "
               "(the file a `--body-file` names is left out). `checks.py run` executes the command the repository's "
               "default branch declares, with your shell's permissions; in a clone you do not trust, show the user "
               "that command before running it")
    if mode == "observe":
        log(common, {**entry, "decision": "would_block"})
        return note(f"{TAG} observe: this PR would be blocked: {problem}.")
    with cg.Locked(counter, {}) as c:
        n = c.get(key, 0)
        released = n >= RELEASE_AFTER
        if released:
            c.pop(key, None)
        else:
            c[key] = n + 1
    if released:
        log(common, {**entry, "decision": "released"})
        return note(f"{TAG} let through after {RELEASE_AFTER} blocks in this session (logged as released): {problem}.")
    log(common, {**entry, "decision": "would_block"})
    return "deny", "\n".join(notes + [
        f"{TAG} PR blocked ({n + 1}/{RELEASE_AFTER}; after {RELEASE_AFTER} blocks in a session the next "
        f"one is let through): {problem}."])


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
    others = untracked(top)
    without = {}
    if len(others) <= MAX_WITHOUT:  # so the PR body file, if it is one of them, can be edited without losing the pass
        without = {p: f for p in others for f in [cg.fingerprint(top, exclude=[p])] if f}
    try:
        record_pass(common, after, command, without)
    except OSError as e:
        print(f"{TAG} passed, but the pass could not be written ({e}): nothing recorded.", file=sys.stderr)
        return 3
    print(f"{TAG} passed: recorded for {after}.")
    return 0


def report(all_rows=False):
    _, common = cg.repo_of(os.getcwd())
    if not common:
        print(f"{TAG} not inside a git work tree.", file=sys.stderr)
        return 2
    try:
        with open(os.path.join(common, LOG_FILE), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except OSError:
        print("No pr-checks log yet for this repo.")
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
