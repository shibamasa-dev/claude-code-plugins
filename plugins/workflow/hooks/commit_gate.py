#!/usr/bin/env python3
"""commit-gate: check at `git commit` that a review or verification ran on the tree being committed.

Evidence (what counts as "ran"): a verifier skill invoked, seen as
  - UserPromptExpansion `command_name` (typing `/code-review` never reaches the Skill tool hooks), or
  - PostToolUse on the Skill tool, `tool_input.skill`.
A verifier is a name matching the verifiers regex (default `^(code-review|(.+:)?verify-.+|coderabbit:code-review)$`).
Evidence is fresh until the Stop of the turn it was invoked in (fixes made in that turn are covered); at that Stop it
is pinned to the tree's fingerprint. Later it counts, for any session, only while the fingerprint is unchanged.
Evidence of this session on an earlier tree is stale (stale is per session; another session's old review says nothing).

Stamp: the commit message carries a `Verification:` trailer, which this hook checks against its own record:
  Verification: review — code-review            (kinds: review / verify; names: the verifiers that ran)
  Verification: none — <reason>                 (an explanation; allowed and logged as explained)
Query unverified commits with `git log origin/<default> --grep='^Verification: none'`.

Modes (`off` / `observe` / `enforce`): `.claude/verification.json` {"commitGate": ..., "verifiers": ...} on origin's
default branch, else userConfig `commit_gate` / `commit_gate_verifiers`, else off. The repo file is read from
`refs/remotes/origin/HEAD` (never the working tree, so a branch cannot change the rule it is judged by); without an
origin remote the working tree is read. When origin's default branch is unknown locally (no origin/HEAD), it does not gate.
  off      nothing is read or written, nothing is said
  observe  never blocks; says what it would have done and logs it (stale evidence: allowed, marked "(stale)")
  enforce  denies a commit with missing or stale evidence, or a trailer the record does not back.
           After two denials in a session, the next commit is allowed (logged as released) and the count resets.

Fingerprint: a hash of `git diff --raw` between merge-base(HEAD, origin/HEAD) and the working tree including untracked
files (through a temporary index and object directory, so nothing is written to the repo). Partial commits, pushes and
clean rebases keep it; any edit, by any tool, changes it. Without a merge-base it is the tree hash.

After a successful `git commit` (PostToolUse) it logs the commit and whether its stamp is backed by the record.
A command that mentions git commit but cannot be lexed is not checked; with the gate on, that is logged and said.
No network on the per-call path. SessionStart asks origin once for its default branch, only when userConfig turns the gate on.
State: state_dir() (see there). Log: state_dir()/log.jsonl. `commit_gate.py report` lists what would have been blocked.
Whatever happens it never raises and exits 0.
"""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell import HEREDOC_MARK_RE, commands, lex  # noqa: E402

TAG = "[commit-gate]"
MODES = ("off", "observe", "enforce")
DEFAULT_VERIFIERS = r"^(code-review|(.+:)?verify-.+|coderabbit:code-review)$"
RELEASE_AFTER = 2          # denials in a session before the next commit is let through
CONFIG = ".claude/verification.json"
MISS_FILE = "commit-gate-origin-miss"   # in the git common dir; its mtime is the last failed network attempt
MISS_TTL = 3600
GC_DAYS = 30
_REPO_SELECT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                     "GIT_ALTERNATE_OBJECT_DIRECTORIES")
GIT_ENV = {**{k: v for k, v in os.environ.items() if k not in _REPO_SELECT_VARS},
           "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
# Within a line only [ \t], so an empty reason cannot borrow the next line
TRAILER_RE = re.compile(r"^[ \t]*Verification:[ \t]*(\S.*?)[ \t]*$", re.M | re.I)
SEP_RE = re.compile(r"[ \t]+[—–-]+[ \t]+|[ \t]*[—–][ \t]*")


def state_dir():
    """The one place that decides where state lives (#83 will move all hook state to CLAUDE_PLUGIN_DATA only)."""
    return os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/.claude/state"), "commit-gate")


def now():
    return datetime.now().isoformat(timespec="seconds")


def git(cwd, *args, env=None, timeout=10):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout,
                           env=env or GIT_ENV, stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return 1, ""


# ------------------------------------------------------------------ repo and settings
def repo_of(cwd):
    """(toplevel, git common dir) or (None, None) outside a work tree."""
    rc, out = git(cwd or ".", "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir")
    lines = out.split("\n")
    if rc != 0 or len(lines) != 2:
        return None, None
    return lines[0], lines[1]


def repo_key(common):
    return hashlib.sha1(common.encode()).hexdigest()[:16]


def repo_config(top):
    """(config dict, source). Read from origin's default branch through the local origin/HEAD (no network).
    source: "default-branch", "working-tree" (no origin remote) or "unknown" (origin/HEAD missing or dangling)."""
    rc, text = git(top, "show", f"refs/remotes/origin/HEAD:{CONFIG}")
    if rc != 0:
        if git(top, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/HEAD^{commit}")[0] == 0:
            return {}, "default-branch"  # not on the default branch: not opted in there
        if git(top, "remote", "get-url", "origin")[0] == 0:
            return {}, "unknown"
        try:
            with open(os.path.join(top, CONFIG), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return {}, "working-tree"
        source = "working-tree"
    else:
        source = "default-branch"
    try:
        cfg = json.loads(text)
        return (cfg if isinstance(cfg, dict) else {}), source
    except ValueError:
        return {}, source


def norm_mode(v):
    v = v.strip().lower() if isinstance(v, str) else ""  # a non-string (true, 1) is not a mode
    return v if v in MODES else "off"


def settings(top):
    """{"mode", "verifiers", "source"}. The repo file on the default branch wins over userConfig; unknown values are off."""
    cfg, source = repo_config(top)
    user_mode = norm_mode(os.environ.get("CLAUDE_PLUGIN_OPTION_COMMIT_GATE"))
    repo_mode = cfg.get("commitGate")
    valid = isinstance(repo_mode, str) and repo_mode.strip().lower() in MODES
    mode = norm_mode(repo_mode) if valid else user_mode  # an unreadable repo value does not switch the gate off
    pattern = cfg.get("verifiers") if isinstance(cfg.get("verifiers"), str) else None
    pattern = pattern or os.environ.get("CLAUDE_PLUGIN_OPTION_COMMIT_GATE_VERIFIERS") or DEFAULT_VERIFIERS
    try:
        verifiers = re.compile(pattern)
    except (re.error, TypeError):
        verifiers = re.compile(DEFAULT_VERIFIERS)
    if source == "unknown":
        mode = "off" if user_mode == "off" else "unknown"
    return {"mode": mode, "verifiers": verifiers, "source": source}


def _miss_path(common):
    return os.path.join(common, MISS_FILE)


def warm_default_branch(top, common):
    """SessionStart only: when the local origin/HEAD is missing or dangling, ask origin once (5 s, no prompt) and save
    the answer as origin/HEAD. A failure is remembered for MISS_TTL. Never guesses main/master."""
    if git(top, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/HEAD^{commit}")[0] == 0:
        return
    if git(top, "remote", "get-url", "origin")[0] != 0:
        return
    try:
        if time.time() - os.path.getmtime(_miss_path(common)) < MISS_TTL:
            return
    except OSError:
        pass
    rc, out = git(top, "ls-remote", "--symref", "origin", "HEAD", timeout=5)
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", out, re.M) if rc == 0 else None
    if m:
        name = m.group(1)
        if git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}")[0] != 0:
            git(top, "fetch", "--quiet", "origin", "--", f"+refs/heads/{name}:refs/remotes/origin/{name}", timeout=5)
        if git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}")[0] == 0:
            git(top, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{name}")
            return
    try:
        with open(_miss_path(common), "a"):
            pass
        os.utime(_miss_path(common))
    except OSError:
        pass


# ------------------------------------------------------------------ fingerprint
def fingerprint(top):
    """A hash of the working tree's change against merge-base(HEAD, origin/HEAD), untracked files included.
    Uses a temporary index and object directory (the repo's objects as an alternate), so nothing is written to the repo.
    None when it cannot be computed in time."""
    tmp = tempfile.mkdtemp(prefix="commit-gate-")
    try:
        _, idx = git(top, "rev-parse", "--path-format=absolute", "--git-path", "index")
        _, objs = git(top, "rev-parse", "--path-format=absolute", "--git-path", "objects")
        env = {**GIT_ENV, "GIT_INDEX_FILE": os.path.join(tmp, "index"),
               "GIT_OBJECT_DIRECTORY": os.path.join(tmp, "objects"), "GIT_ALTERNATE_OBJECT_DIRECTORIES": objs}
        os.makedirs(env["GIT_OBJECT_DIRECTORY"])
        if os.path.exists(idx):
            shutil.copyfile(idx, env["GIT_INDEX_FILE"])  # keeps the stat cache, so `add -A` rehashes only changed files
        if git(top, "add", "-A", env=env, timeout=20)[0] != 0:
            return None
        rc, tree = git(top, "write-tree", env=env)
        if rc != 0:
            return None
        rc, mb = git(top, "merge-base", "HEAD", "refs/remotes/origin/HEAD")
        if rc != 0 or not mb:
            return "tree:" + tree[:16]
        rc, raw = git(top, "diff", "--raw", "--no-abbrev", "--no-renames", mb, tree, env=env, timeout=20)
        if rc != 0:
            return None
        return "diff:" + hashlib.sha1(raw.encode()).hexdigest()[:16]
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ state
class Locked:
    """Read-modify-write of one JSON file under flock (parallel tool calls and sessions may arrive together)."""

    def __init__(self, path, default):
        self.p, self.default = path, default

    def __enter__(self):
        os.makedirs(os.path.dirname(self.p), exist_ok=True)
        self.lf = open(self.p + ".lock", "w")
        fcntl.flock(self.lf, fcntl.LOCK_EX)
        try:
            with open(self.p) as f:
                self.d = json.load(f)
        except Exception:
            self.d = json.loads(json.dumps(self.default))
        return self.d

    def __exit__(self, *a):
        tmp = self.p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p)
        fcntl.flock(self.lf, fcntl.LOCK_UN)
        self.lf.close()


def repo_path(key):
    return os.path.join(state_dir(), "repos", key + ".json")


def pending_path(sid):
    return os.path.join(state_dir(), "pending", re.sub(r"[^\w.-]", "_", sid) + ".json")


REPO_DEFAULT = {"evidence": {}, "seen": {}, "blocks": {}}   # seen and blocks are keyed by session


def log(entry):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(os.path.join(state_dir(), "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": now(), **entry}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def gc():
    cutoff = time.time() - GC_DAYS * 86400
    for sub in ("pending", "repos", "heads"):
        d = os.path.join(state_dir(), sub)
        try:
            for n in os.listdir(d):
                fp = os.path.join(d, n)
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
        except OSError:
            pass


# ------------------------------------------------------------------ evidence
def record_invocation(inp, name):
    """A verifier was invoked: remember it for this session's current turn (pinned at Stop)."""
    if not name:
        return None
    top, common = repo_of(inp.get("cwd"))
    if not top:
        return None
    s = settings(top)
    if s["mode"] in ("off", "unknown") or not s["verifiers"].search(name):
        return None
    key = repo_key(common)
    with Locked(pending_path(inp["session_id"]), {}) as p:
        ent = p.setdefault(key, {"top": top, "prompt_id": inp.get("prompt_id"), "names": []})
        if ent.get("prompt_id") != inp.get("prompt_id"):
            ent.update(prompt_id=inp.get("prompt_id"), names=[], carried=sorted(set(ent.get("carried", []) + ent["names"])))
        if name not in ent["names"]:
            ent["names"].append(name)
    return None


def on_stop(inp):
    """Pin this turn's evidence to the fingerprint at this moment. Evidence from an earlier turn that never reached
    a Stop is not pinned (the tree may have moved since); it only counts as seen (= stale)."""
    pp = pending_path(inp["session_id"])
    if not os.path.exists(pp):
        return None  # nothing recorded for this session: no git, no state read
    with Locked(pp, {}) as p:
        pend = dict(p)
        p.clear()
    try:
        os.remove(pp)
    except OSError:
        pass
    for key, ent in pend.items():
        this_turn = ent.get("prompt_id") == inp.get("prompt_id")
        fp = fingerprint(ent["top"]) if this_turn and ent.get("names") else None
        with Locked(repo_path(key), REPO_DEFAULT) as r:
            seen = r["seen"].setdefault(inp["session_id"], {})
            for name in ent.get("names", []) + ent.get("carried", []):
                seen[name] = now()
            if fp:
                ev = r["evidence"].setdefault(fp, {})
                for name in ent["names"]:
                    ev[name] = now()
                r["evidence"] = dict(sorted(r["evidence"].items(), key=lambda kv: max(kv[1].values()))[-50:])
    return None


# ------------------------------------------------------------------ git commit parsing
_GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
_COMMIT_SHORT_VALUE = "mFCct"  # short options of git commit that take a value
_COMMIT_SHORT_FLAGS = set("aqsvenzpio")  # short options that take none (a cluster with anything else is not trusted)


def git_commits(command, cwd):
    """The `git commit` calls in a Bash command: [{"cwd", "args", "call"}]."""
    out = []
    for call in commands(command, {"git"}, cwd):
        args, i, here = call["args"], 0, call["cwd"]
        while i < len(args) and args[i].startswith("-"):
            a = args[i]
            if a == "-C" and i + 1 < len(args):
                d = os.path.expanduser(args[i + 1])
                if "$" in d or "`" in d:
                    here = None  # unknown (a variable or command substitution): the hook's cwd is used
                else:
                    here = d if os.path.isabs(d) else (os.path.join(here, d) if here else None)
                i += 2
            elif a in _GIT_VALUE_OPTS and "=" not in a:
                i += 2
            else:
                i += 1
        if i < len(args) and args[i] == "commit":
            out.append({"cwd": here, "args": args[i + 1:], "call": call})
    return out


def _read(path, cwd):
    p = path if os.path.isabs(path) else os.path.join(cwd or ".", path)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _msg_value(v, call):
    m = HEREDOC_MARK_RE.search(v)
    if m:
        return call["docs"][int(m.group(1))]  # -m "$(cat <<'EOF' ... EOF)"
    return None if re.fullmatch(r"\s*\$\{?\w+\}?\s*", v) else v


def _add(parts, text):
    """Append text when known. True when it is not (the message then cannot be inspected)."""
    if text is None:
        return True
    parts.append(text)
    return False


def commit_message(c, top):
    """(message or None, dry_run). None when the message cannot be inspected (a variable, the editor, piped stdin)."""
    args, call, cwd = c["args"], c["call"], c["cwd"] or top
    parts, trailers, src, amend, dry, unknown = [], [], None, False, False, False
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        if a == "--":
            break
        if a.startswith("--"):
            k, eq, v = a.partition("=")
            takes = k in ("--message", "--file", "--reuse-message", "--reedit-message", "--trailer", "--template",
                          "--fixup", "--squash", "--author", "--date", "--cleanup")
            if takes and not eq:
                v, i = (nxt or ""), i + 1
            if k == "--message":
                unknown |= _add(parts, _msg_value(v, call))
            elif k == "--file":
                src = ("file", v)
            elif k in ("--reuse-message", "--reedit-message"):
                src = ("commit", v)
            elif k == "--trailer":
                trailers.append(v)
            elif k == "--amend":
                amend = True
            elif k == "--dry-run":
                dry = True
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], 1):
                if ch in _COMMIT_SHORT_VALUE:
                    v = a[j + 1:]
                    if not v:
                        v, i = (nxt or ""), i + 1
                    if ch == "m":
                        unknown |= _add(parts, _msg_value(v, call))
                    elif ch == "F":
                        src = ("file", v)
                    elif ch in "Cc":
                        src = ("commit", v)
                    break
        i += 1
    if src and src[0] == "file":
        if src[1] in ("-", "/dev/stdin"):
            body = call["docs"][call["stdin"]] if call["stdin"] is not None else None
        else:
            body = _read(src[1], cwd)
        unknown |= _add(parts, body)
    elif src and src[0] == "commit":
        # Resolve to a commit id first, so a value such as `--output=x` never reaches git log as an option
        body = None
        rc, sha = git(top, "rev-parse", "--verify", "--quiet", "--end-of-options", src[1] + "^{commit}")
        if rc == 0 and re.fullmatch(r"[0-9a-f]{40,64}", sha):
            rc, body = git(top, "log", "-1", "--format=%B", sha, "--")
        else:
            rc = 1
        unknown |= _add(parts, body if rc == 0 else None)
    elif not parts and amend:
        rc, body = git(top, "log", "-1", "--format=%B", "HEAD")  # --amend without a new message keeps HEAD's
        unknown |= _add(parts, body if rc == 0 else None)
    trailers = [re.sub(r"^\s*([\w-]+)\s*=\s*", r"\1: ", t) for t in trailers]  # --trailer key=value
    if unknown or not parts:
        # The body cannot be read (or comes from the editor): only --trailer lines are known
        return ("\n".join(trailers) or None), dry
    return "\n\n".join(parts) + "".join("\n" + t for t in trailers), dry


def parse_trailer(msg):
    """None | ("none", reason) | ("names", [names], marked_stale). The last `Verification:` line wins."""
    found = TRAILER_RE.findall(msg or "")
    if not found:
        return None
    parts = SEP_RE.split(found[-1], 1)
    if len(parts) != 2:
        return None
    kinds, rest = parts[0].strip().lower(), parts[1].strip()
    if kinds == "none":
        return ("none", rest) if rest else None
    names, stale = [], False
    for n in rest.split(","):
        n = n.strip()
        if n.lower().endswith("(stale)"):
            stale, n = True, n[:-7].strip()
        if n:
            names.append(n)
    return ("names", names, stale) if names else None


def kind_of(name):
    return "verify" if re.search(r"(?:^|:)verify-", name) else "review"


def suggest(names, stale=False):
    names = sorted(names)
    kinds = ", ".join(sorted({kind_of(n) for n in names}))
    return f"Verification: {kinds} — " + ", ".join(n + (" (stale)" if stale else "") for n in names)


# ------------------------------------------------------------------ decision
def judge(trailer, fresh, stale):
    """(verdict, problem). verdict: allow / explained / would_block / stale. problem: the text for a block."""
    none_line = "`Verification: none — <reason>`"
    if trailer and trailer[0] == "none":
        return "explained", None
    if trailer:
        claimed = set(trailer[1])
        unbacked = claimed - fresh - stale
        if unbacked:
            return "would_block", (f"the trailer names {', '.join(sorted(unbacked))}, but this session has no record of "
                                   "it running. Run it, or write " + none_line)
        if claimed <= fresh:
            return "allow", None
        return "stale", (f"{', '.join(sorted(claimed - fresh))} ran on an earlier state of the tree (it changed since). "
                         f"Run it again, or write {none_line}")
    if fresh:
        return "would_block", f"no `Verification:` trailer. Add this line to the message: `{suggest(fresh)}`"
    if stale:
        return "stale", (f"{', '.join(sorted(stale))} ran on an earlier state of the tree (it changed since). "
                         f"Run it again, or write {none_line}")
    return "would_block", ("no review or verification ran on this tree. Run one (for example /code-review, or the "
                           f"repo's verify-* skills), or write {none_line} in the message")


def evidence_for(key, sid, prompt_id, fp):
    """(fresh names, stale names, repo state) for this tree."""
    try:
        with open(repo_path(key)) as f:
            r = json.load(f)
    except Exception:
        r = json.loads(json.dumps(REPO_DEFAULT))
    fresh = set((r.get("evidence") or {}).get(fp, {})) if fp else set()
    seen = set((r.get("seen") or {}).get(sid, {}))  # stale is per session: another branch's review says nothing here
    try:
        with open(pending_path(sid)) as f:
            ent = json.load(f).get(key) or {}
    except Exception:
        ent = {}
    if ent.get("prompt_id") == prompt_id:
        fresh |= set(ent.get("names", []))   # invoked in this turn: covers fixes made before the Stop
        seen |= set(ent.get("carried", []))
    else:
        seen |= set(ent.get("names", [])) | set(ent.get("carried", []))
    return fresh, seen - fresh


def on_pre_bash(inp):
    cmd = (inp.get("tool_input") or {}).get("command", "")
    if "commit" not in cmd or "git" not in cmd:
        return None
    calls = git_commits(cmd, inp.get("cwd"))
    if not calls:
        if lex(cmd) is None and re.search(r"\bgit\b.*\bcommit\b", cmd):
            return unparsed(inp, cmd)
        return None
    notes, denial = [], None
    for c in calls:
        top, common = repo_of(c["cwd"] or inp.get("cwd"))
        if not top:
            continue
        s = settings(top)
        if s["mode"] == "off":
            continue
        if s["mode"] == "unknown":
            log({"session": inp["session_id"], "repo": top, "branch": branch_of(top), "mode": "unknown",
                 "decision": "nogate", "cmd": cmd[:200]})
            notes.append(f"{TAG} cannot tell origin's default branch (no local origin/HEAD), so the repo's {CONFIG} "
                         "cannot be read: not gating. `git remote set-head origin --auto` fixes it.")
            continue
        if s["source"] == "working-tree":
            notes.append(f"{TAG} no origin remote: {CONFIG} is read from the working tree.")
        msg, dry = commit_message(c, top)
        if dry:
            continue
        res = decide(inp, s, top, common, msg, cmd, commits_all(c["args"]))
        if res and res[0] == "deny":
            denial = res[1]
            break
        if res:
            notes.append(res[1])
    if denial:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": denial}}
    if notes:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n".join(notes)}}
    return None


def branch_of(top):
    rc, b = git(top, "rev-parse", "--abbrev-ref", "HEAD")
    return b if rc == 0 else None


def unparsed(inp, cmd):
    """A command that mentions git commit but cannot be lexed: not checked. Logged and said when the gate is on."""
    top, _ = repo_of(inp.get("cwd"))
    if not top or settings(top)["mode"] in ("off", "unknown"):
        return None
    log({"session": inp["session_id"], "repo": top, "branch": branch_of(top), "decision": "unparsed", "cmd": cmd[:200]})
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
            f"{TAG} could not read this command (unbalanced quotes?), so the commit was not checked."}}


def on_post_bash(inp):
    """After a successful git commit, log the commit and whether its stamp is backed by the record (section 2's
    observe step). The PreToolUse log has the attempts; this one has the commits that were made."""
    cmd = (inp.get("tool_input") or {}).get("command", "")
    if "commit" not in cmd or "git" not in cmd:
        return None
    calls = git_commits(cmd, inp.get("cwd"))
    hp = heads_path(inp["session_id"])
    if not calls or not os.path.exists(hp):
        return None  # no checked commit in this session (the gate is off, or PreToolUse did not get that far)
    top, common = repo_of(calls[0]["cwd"] or inp.get("cwd"))
    if not top:
        return None
    with Locked(hp, {}) as h:
        before = h.pop(top, None)
    rc, sha = git(top, "rev-parse", "--verify", "--quiet", "HEAD")
    if before is None or rc != 0 or sha == before:
        return None  # HEAD did not move: the commit failed or was refused
    _, body = git(top, "log", "-1", "--format=%B", sha, "--")
    trailer = parse_trailer(body)
    fresh, _ = evidence_for(repo_key(common), inp["session_id"], inp.get("prompt_id"), fingerprint(top))
    backed = bool(trailer) and (trailer[0] == "none" or set(trailer[1]) <= fresh)
    log({"session": inp["session_id"], "repo": top, "branch": branch_of(top), "decision": "committed", "sha": sha,
         "trailer": (TRAILER_RE.findall(body) or [None])[-1], "stamp": "backed" if backed else
         ("missing" if not trailer else "unbacked"), "cmd": cmd[:200]})
    return None


def staged_differs(top):
    """Paths whose staged content differs both from HEAD and from the working tree (staged, then edited again).
    ["(git diff failed)"] when either side cannot be read, so the check fails closed."""
    rc1, staged = git(top, "diff", "--cached", "--name-only", "-z")
    rc2, unstaged = git(top, "diff", "--name-only", "-z")
    if rc1 != 0 or rc2 != 0:
        return ["(git diff failed)"]
    both = set(filter(None, staged.split("\0"))) & set(filter(None, unstaged.split("\0")))
    return sorted(both)


def commits_all(args):
    """True when the commit stages tracked changes itself (`-a` / `--all`), so the index is not committed as it is."""
    for a in args:
        if a == "--":
            break
        if a == "--all":
            return True
        if a.startswith("-") and not a.startswith("--"):
            for ch in a[1:]:
                if ch in _COMMIT_SHORT_VALUE:
                    break  # the rest is that option's value (as in -mall)
                if ch not in _COMMIT_SHORT_FLAGS:
                    break  # -u<mode>, -S<key> and unknown letters: the rest may be a value (as in -unormal)
                if ch == "a":
                    return True
    return False


def heads_path(sid):
    return os.path.join(state_dir(), "heads", re.sub(r"[^\w.-]", "_", sid) + ".json")


def remember_head(sid, top):
    """HEAD before a checked commit, so PostToolUse can tell that a commit happened (`-q` prints no summary)."""
    _, head = git(top, "rev-parse", "--verify", "--quiet", "HEAD")
    with Locked(heads_path(sid), {}) as h:
        h[top] = head


def decide(inp, s, top, common, msg, cmd, stages_all=False):
    """("deny", reason) | ("note", text) | None."""
    sid, mode, key = inp["session_id"], s["mode"], repo_key(common)
    fp = fingerprint(top)
    trailer = parse_trailer(msg)
    entry = {"session": sid, "repo": top, "branch": branch_of(top), "mode": mode, "fingerprint": fp,
             "trailer": (TRAILER_RE.findall(msg or "") or [None])[-1], "cmd": cmd[:200]}
    if fp is None:
        log({**entry, "decision": "unchecked"})
        return "note", f"{TAG} could not fingerprint the tree in time: not checked."
    fresh, stale = evidence_for(key, sid, inp.get("prompt_id"), fp)
    verdict, problem = judge(trailer, fresh, stale)
    entry["verifiers"] = sorted(fresh)
    remember_head(sid, top)
    if verdict == "allow" and not stages_all:
        split = staged_differs(top)
        if split:
            verdict, problem = "would_block", (
                f"the staged version of {', '.join(split[:5])} differs from the working tree, which is what was verified; "
                "the commit would record the staged one. Stage it again (`git add`), or write `Verification: none \u2014 <reason>`")
    if verdict in ("allow", "explained"):
        with Locked(repo_path(key), REPO_DEFAULT) as r:
            r["blocks"].pop(sid, None)
        log({**entry, "decision": verdict})
        return None
    if verdict == "stale" and mode == "observe":
        log({**entry, "decision": "stale"})
        hint = f" Mark the trailer `{suggest(stale, stale=True)}`." if not trailer else ""
        return "note", f"{TAG} observe: stale evidence, allowed: {problem}.{hint}"
    with Locked(repo_path(key), REPO_DEFAULT) as r:
        n = r["blocks"].get(sid, 0)
        if n >= RELEASE_AFTER:
            r["blocks"].pop(sid, None)
            released = True
        else:
            r["blocks"][sid] = n + 1
            released = False
    if released:
        log({**entry, "decision": "released"})
        return "note", (f"{TAG} {'observe: ' if mode == 'observe' else ''}let through after {RELEASE_AFTER} blocks "
                        f"in this session (logged as released): {problem}.")
    log({**entry, "decision": "would_block"})
    if mode == "observe":
        return "note", f"{TAG} observe: this commit would be blocked ({n + 1}/{RELEASE_AFTER}): {problem}."
    return "deny", (f"{TAG} Commit blocked ({n + 1}/{RELEASE_AFTER}; after {RELEASE_AFTER} blocks in a session the next "
                    f"commit is let through): {problem}.")


# ------------------------------------------------------------------ main
def report(all_rows=False):
    try:
        with open(os.path.join(state_dir(), "log.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except OSError:
        print("No commit-gate log yet.")
        return 0
    for r in rows:
        if all_rows or r.get("decision") in ("would_block", "stale", "released"):
            print(f"{r.get('ts')} {r.get('mode')} {r.get('decision')} {r.get('repo')} trailer={r.get('trailer')!r} "
                  f"verifiers={','.join(r.get('verifiers') or [])} :: {r.get('cmd')}")
    return 0


def main():
    if sys.argv[1:2] == ["report"]:
        return report("--all" in sys.argv[2:])
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return 0
    if not inp.get("session_id"):
        return 0
    ev = inp.get("hook_event_name", "")
    try:
        out = None
        if ev == "PreToolUse" and inp.get("tool_name") == "Bash":
            out = on_pre_bash(inp)
        elif ev == "PostToolUse" and inp.get("tool_name") == "Bash":
            out = on_post_bash(inp)
        elif ev == "UserPromptExpansion":
            out = record_invocation(inp, inp.get("command_name"))
        elif ev == "PostToolUse" and inp.get("tool_name") == "Skill":
            out = record_invocation(inp, (inp.get("tool_input") or {}).get("skill"))
        elif ev == "Stop":
            out = on_stop(inp)
        elif ev == "SessionStart":
            if norm_mode(os.environ.get("CLAUDE_PLUGIN_OPTION_COMMIT_GATE")) != "off":
                top, common = repo_of(inp.get("cwd"))
                if top:
                    warm_default_branch(top, common)
            if os.path.isdir(state_dir()):
                gc()
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception as e:  # never stop the work, but leave a trace that the gate did not run
        if os.path.isdir(state_dir()):
            log({"session": inp.get("session_id"), "decision": "error", "event": ev,
                 "error": f"{type(e).__name__}: {e}"[:200]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
