#!/usr/bin/env python3
"""issue-writeback: enforces "write decisions back to the issues you read".

Tracks GitHub issues that were read in the session (issue_read / gh issue view) but not written afterwards
(issue_write update / add_issue_comment / sub_issue_write / gh issue edit|comment|close).
(PRs are not tracked. A read whose result is /pull/N is not recorded, and gh pr edit|comment etc. count as writes,
including the forms with no number or with a branch name.)
  - Stop            : after K turns with no write-back, block once to prompt it (at most MAX_NAGS times per issue)
  - UserPromptSubmit: inject a one-line reminder only while something is pending (no output otherwise)
  - SessionStart    : re-inject pending issues after compact/resume. After clear, notify once that they were cleared while pending
  - SessionEnd      : only on clear, hand pending issues over to a notice file. The state file is kept (exit -> resume brings
                      back the same session_id). Cleanup is an mtime GC after GC_DAYS
State is ~/.claude/state/issue-writeback/<session_id>.json (per session; parallel sessions don't mix).
Whatever happens it never raises and exits 0 (the Stop block is the only output that stops anything).

CLI: issue-writeback dismiss OWNER/REPO#N --session <id> [--why "..."]   # run by Claude
     issue-writeback status [--pending]                                   # tracking status of all sessions (joined with claude agents --json)
"""
import fcntl, hashlib, json, os, re, sys, time
from datetime import datetime, timedelta

STATE_DIR = os.path.expanduser("~/.claude/state/issue-writeback")
K_STOPS = 3          # block after this many Stops since the read (or since the last nag)
MAX_NAGS = 3         # max blocks per issue (silent after that)
GC_DAYS = 30         # clean up old state files (not deleted at SessionEnd, since resume brings back the same session_id)
CLEAR_NOTICE_TTL = 600  # seconds a clear notice stays valid

# ---------------------------------------------------------------- state io
def _path(session_id): return os.path.join(STATE_DIR, f"{session_id}.json")

class State:
    """Read-modify-write under flock. Safe when parallel tool calls arrive at the same time."""
    def __init__(self, session_id):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.p = _path(session_id); self.lock = self.p + ".lock"
    def __enter__(self):
        self.lf = open(self.lock, "w"); fcntl.flock(self.lf, fcntl.LOCK_EX)
        try:
            with open(self.p) as f: self.d = json.load(f)
        except Exception:
            self.d = {"issues": {}}
        return self
    def __exit__(self, *a):
        tmp = self.p + ".tmp"
        with open(tmp, "w") as f: json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p)
        fcntl.flock(self.lf, fcntl.LOCK_UN); self.lf.close()

def now(): return datetime.now().isoformat(timespec="seconds")

def pending(d):
    return {k: v for k, v in d.get("issues", {}).items()
            if v.get("read_at") and not v.get("written_at") and not v.get("dismissed")}

# ------------------------------------------------------------- ref parsing
def repo_from_cwd(cwd):
    try:
        import subprocess
        r = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=2)
        m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", r.stdout.strip())
        if m: return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return None

def refs_from_mcp(tool_name, ti):
    """(kind, ref) with kind in {read, write, None}"""
    base = tool_name.rsplit("__", 1)[-1]
    o, r, n = ti.get("owner"), ti.get("repo"), ti.get("issue_number")
    if not (o and r and n): return None, None
    ref = f"{o}/{r}#{int(n)}"
    if base == "issue_read": return "read", ref
    if base == "issue_write" and ti.get("method") == "update": return "write", ref
    if base == "add_issue_comment" and ti.get("body"): return "write", ref
    if base == "sub_issue_write": return "write", ref
    return None, None

def is_pr_response(ref, tr):
    """If the read result contains `github.com/OWNER/REPO/pull/N`, that number is a PR.
    issue_read and `gh api repos/.../issues/N` (PR comments use this API too) can read PRs as well,
    but a PR's write-back target is the response table in its body, which issue-writeback does not cover."""
    repo, n = ref.rsplit("#", 1)
    text = tr if isinstance(tr, str) else json.dumps(tr, ensure_ascii=False)
    return re.search(rf"github\.com/{re.escape(repo)}/pull/{n}(?!\d)", text, re.I) is not None

_GH_REPO = r"(?:-R\s*=?\s*|--repo(?:\s+|=))([\w.-]+/[\w.-]+)"  # -R o/r, -Ro/r, --repo o/r, --repo=o/r
# Options of the writing gh pr subcommands that take the next argument as a value (-R/--repo are shared).
# The same short option can mean different things per subcommand (close -c takes a value, review -c does not), so keep them apart
_PR_VALUE_FLAGS = {
    "edit": {"-b", "--body", "-F", "--body-file", "--attach", "-t", "--title", "-B", "--base", "-m", "--milestone",
             "--add-assignee", "--remove-assignee", "--add-label", "--remove-label",
             "--add-project", "--remove-project", "--add-reviewer", "--remove-reviewer"},
    "comment": {"-b", "--body", "-F", "--body-file", "--attach"},
    "close": {"-c", "--comment"},
    "reopen": {"-c", "--comment"},
    "merge": {"-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email", "--match-head-commit"},
    "review": {"-b", "--body", "-F", "--body-file"},
    "ready": set(),
}

def _pr_selector(sub, rest):
    """Extract the PR selector (number, URL or branch) after `gh pr <sub>`. None if absent (the current branch's PR)."""
    import shlex
    try:
        toks = shlex.split(rest)
    except ValueError:
        toks = rest.split()
    flags = _PR_VALUE_FLAGS[sub] | {"-R", "--repo"}
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "--":
            return toks[i + 1] if i + 1 < len(toks) else None
        if t.startswith("-") and len(t) > 1:
            i += 2 if (t in flags and "=" not in t) else 1
            continue
        return t
    return None

def _resolve_pr(sel, repo, cwd, tr):
    """Resolve the number of a PR not given by number or URL (current branch or a branch name): from the output first, then `gh pr view`."""
    out = (tr.get("stdout") or "") if isinstance(tr, dict) else (tr if isinstance(tr, str) else "")
    if repo:
        m = re.search(rf"github\.com/{re.escape(repo)}/pull/(\d+)|\b{re.escape(repo)}#(\d+)\b", out, re.I)
        if m: return f"{repo}#{m.group(1) or m.group(2)}"
    try:
        import subprocess
        args = ["gh", "pr", "view"] + ([sel] if sel else []) + (["-R", repo] if repo else []) + \
               ["--json", "number,url", "--jq", ".url"]
        r = subprocess.run(args, cwd=cwd or None, capture_output=True, text=True, timeout=5)
        m = re.search(r"github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", r.stdout)
        if m: return f"{m.group(1)}#{m.group(2)}"
    except Exception:
        pass
    return None

def refs_from_bash(cmd, cwd, tr=None):
    out = []
    for seg in re.split(r"[|;&]+|\n", cmd):
        # PRs are not tracked (a PR's write-back target is the response table in its body, handled by pr-review-triage).
        # But if a PR read through the issues API was recorded, a write to that PR clears it.
        # A PR can be named by a number, URL or branch name after the options, or not at all (the current branch)
        m = re.search(r"\bgh\s+pr\s+(edit|comment|close|reopen|merge|review|ready)\b(.*)", seg)
        if m:
            sel = _pr_selector(m.group(1), m.group(2))
            um = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)(?:[/?#].*)?", sel or "")
            if um:
                out.append(("write", f"{um.group(1)}#{um.group(2)}")); continue
            rm = re.search(_GH_REPO, seg); repo = rm.group(1) if rm else repo_from_cwd(cwd)
            nm = re.fullmatch(r"#?(\d+)", sel or "")
            if nm:
                if repo: out.append(("write", f"{repo}#{nm.group(1)}"))
            else:
                ref = _resolve_pr(sel, repo, cwd, tr)
                if ref: out.append(("write", ref))
            continue
        m = re.search(r"\bgh\s+issue\s+(view|edit|comment|close|reopen)\s+(?:#?(\d+)|(https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)))", seg)
        if m:
            kind = "read" if m.group(1) == "view" else "write"
            if m.group(3):
                out.append((kind, f"{m.group(4)}#{m.group(5)}")); continue
            rm = re.search(_GH_REPO, seg); repo = rm.group(1) if rm else repo_from_cwd(cwd)
            if repo: out.append((kind, f"{repo}#{m.group(2)}"))
            continue
        m = re.search(r"\bgh\s+api\b.*?repos/([\w.-]+)/([\w.-]+)/issues/(\d+)", seg)
        if m:
            kind = "write" if re.search(r"-X\s*(POST|PATCH)|--method\s*(POST|PATCH)|(^|\s)-f\s|--field|--input", seg) else "read"
            out.append((kind, f"{m.group(1)}/{m.group(2)}#{m.group(3)}"))
    return out

# ------------------------------------------------------------------ events
def on_post_tool_use(inp):
    tn = inp.get("tool_name", ""); ti = inp.get("tool_input") or {}
    refs = []
    if tn == "Bash":
        tr = inp.get("tool_response") or {}
        refs = refs_from_bash(ti.get("command", ""), inp.get("cwd", ""), tr)
        # A failed gh write does not count as written (only guards against wrongly suppressing the nag; a false read is harmless)
        err = (tr.get("stderr") or "") if isinstance(tr, dict) else ""
        if err and re.search(r"(?i)\b(error|failed|could not|HTTP [45]\d\d|GraphQL)\b", err):
            refs = [(k, r) for k, r in refs if k != "write"]
    elif tn.startswith("mcp__") and tn.rsplit("__", 1)[-1] in ("issue_read", "issue_write", "add_issue_comment", "sub_issue_write"):
        k, ref = refs_from_mcp(tn, ti)
        if k: refs = [(k, ref)]
    tr = inp.get("tool_response")
    if tr:
        refs = [(k, r) for k, r in refs if k != "read" or not is_pr_response(r, tr)]
    if not refs: return
    with State(inp["session_id"]) as st:
        st.d["cwd"] = inp.get("cwd")
        for kind, ref in refs:
            it = st.d["issues"].setdefault(ref, {"read_at": None, "written_at": None, "dismissed": None, "stops_since": 0, "nags": 0})
            if kind == "read":
                it["read_at"] = it["read_at"] or now()
            else:
                it["written_at"] = now(); it["stops_since"] = 0

def on_stop(inp):
    if inp.get("stop_hook_active"): return
    if not os.path.exists(_path(inp["session_id"])): return  # don't create an empty file for a session that read no issue
    with State(inp["session_id"]) as st:
        due = []
        for ref, it in pending(st.d).items():
            it["stops_since"] = it.get("stops_since", 0) + 1
            if it["stops_since"] >= K_STOPS and it.get("nags", 0) < MAX_NAGS:
                due.append(ref); it["stops_since"] = 0; it["nags"] = it.get("nags", 0) + 1
    if not due: return
    sid = inp["session_id"]
    lines = [f"[issue-writeback] You read {', '.join(due)} but have not updated the issue since. "
             "If this conversation decided anything or changed an assumption, write it back now: "
             "rewrite the body for the current design, remaining tasks and done criteria (\"where things stand now\"), "
             "and add a comment for the history and reasons (\"why it ended up this way\"). "
             "If there really is nothing to write back, run the following to record why, then end:"]
    for ref in due:
        lines.append(f"  issue-writeback dismiss {ref} --session {sid} --why \"<reason>\"")
    reason = "\n".join(lines)
    print(json.dumps({"decision": "block", "reason": reason,
                      "hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": reason}}, ensure_ascii=False))

def on_user_prompt(inp):
    try:
        with open(_path(inp["session_id"])) as f: d = json.load(f)
    except Exception:
        return
    p = pending(d)
    if not p: return
    items = ", ".join(f"{k} (read {v['read_at'][11:16]})" for k, v in p.items())
    print(f"[issue-writeback] Not written back: {items} — write each decision to the body/a comment as soon as it is made (don't batch them at session end)")

def gc():
    try:
        cutoff = time.time() - GC_DAYS * 86400
        for n in os.listdir(STATE_DIR):
            fp = os.path.join(STATE_DIR, n)
            if os.path.getmtime(fp) < cutoff: os.remove(fp)
    except Exception:
        pass

def _clear_notice_path(cwd):
    return os.path.join(STATE_DIR, "clear-" + hashlib.sha1((cwd or "").encode()).hexdigest()[:12] + ".json")

def on_session_start(inp):
    reason = inp.get("reason") or inp.get("source") or ""
    gc()
    if reason == "clear":
        fp = _clear_notice_path(inp.get("cwd", ""))
        try:
            with open(fp) as f: n = json.load(f)
            os.remove(fp)
            if time.time() - n["at"] < CLEAR_NOTICE_TTL and n["pending"]:
                print(f"[issue-writeback] ⚠️ {', '.join(n['pending'])}, read in the previous conversation, was /clear-ed without being written back. "
                      "Any decisions made there may be missing from the issue (this notice appears only once).")
        except Exception:
            pass
        return
    if reason in ("compact", "resume"):
        try:
            with open(_path(inp["session_id"])) as f: d = json.load(f)
        except Exception:
            return
        p = pending(d)
        if p:
            hint = "If the summary still holds decisions, do it now:" if reason == "compact" else "If the previous conversation decided anything, before continuing:"
            print(f"[issue-writeback] {', '.join(p)}, read before {reason}, is not written back. {hint} write it to the body/a comment.")

def on_session_end(inp):
    """Keep the state file (resume comes back to it). Only on clear, hand a notice to the next conversation and reset the state."""
    sid = inp["session_id"]; fp = _path(sid)
    if inp.get("reason") != "clear" or not os.path.exists(fp): return
    try:
        with open(fp) as f: d = json.load(f)
        p = list(pending(d))
        if p:
            with open(_clear_notice_path(inp.get("cwd") or d.get("cwd", "")), "w") as f:
                json.dump({"at": time.time(), "pending": p}, f)
    finally:
        for x in (fp, fp + ".lock", fp + ".tmp"):
            try: os.remove(x)
            except Exception: pass

# --------------------------------------------------------------------- cli
def cli_dismiss(argv):
    ref = argv[0]; sid = None; why = ""
    i = 1
    while i < len(argv):
        if argv[i] == "--session": sid = argv[i + 1]; i += 2
        elif argv[i] == "--why": why = argv[i + 1]; i += 2
        else: i += 1
    if not sid:
        print("--session <id> is required (it is in the Stop message)", file=sys.stderr); return 2
    with State(sid) as st:
        it = st.d["issues"].get(ref)
        if not it:
            print(f"{ref} is not tracked in this session", file=sys.stderr); return 1
        it["dismissed"] = {"at": now(), "why": why}
    print(f"dismissed {ref}: {why or '(no reason)'}"); return 0

def cli_status(argv):
    """State files x `claude agents --json --all` -> list session name, alive/ended, and pending issues."""
    import subprocess
    only_pending = "--pending" in argv
    live = {}
    try:
        r = subprocess.run(["claude", "agents", "--json", "--all"], capture_output=True, text=True, timeout=10)
        live = {x["sessionId"]: x for x in json.loads(r.stdout or "[]")}
    except Exception as e:
        print(f"(could not query claude agents: {e} — showing alive/ended as unknown)", file=sys.stderr)
    rows = []
    for n in sorted(os.listdir(STATE_DIR)):
        if not n.endswith(".json") or n.startswith("clear-"): continue
        sid = n[:-5]
        try:
            with open(os.path.join(STATE_DIR, n)) as f: d = json.load(f)
        except Exception:
            continue
        p = pending(d)
        if only_pending and not p: continue
        a = live.get(sid)
        rows.append((0 if a else 1, sid, a, d, p))
    if not rows:
        print("no tracked issues"); return 0
    for _, sid, a, d, p in sorted(rows, key=lambda r: (r[0], r[1])):
        if a:
            head = f"● {a.get('name') or '(unnamed)'}  [{a.get('kind')}/{a.get('status') or '-'}]"
        else:
            head = "○ ended (resumable)"
        print(f"{head}  {sid[:8]}  {d.get('cwd') or ''}")
        for ref, it in d.get("issues", {}).items():
            st = "written back" if it.get("written_at") else ("dismiss: " + (it["dismissed"].get("why") or "-")) if it.get("dismissed") else "★pending"
            when = (it.get("read_at") or it.get("written_at") or "")[5:16]
            print(f"    {ref:<32} {'read ' if it.get('read_at') else 'wrote'} {when}  {st}")
        if p and not a:
            print(f"    → claude --resume {sid}")
    return 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "dismiss":
        sys.exit(cli_dismiss(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        sys.exit(cli_status(sys.argv[2:]))
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    if not inp.get("session_id"): return
    if os.path.exists(os.path.join(STATE_DIR, ".debug")):  # touch state/.debug to log raw input (for debugging)
        with open(os.path.join(STATE_DIR, ".debug.log"), "a") as f:
            f.write(json.dumps(inp, ensure_ascii=False)[:4000] + "\n")
    ev = inp.get("hook_event_name")
    {"PostToolUse": on_post_tool_use, "Stop": on_stop, "UserPromptSubmit": on_user_prompt,
     "SessionStart": on_session_start, "SessionEnd": on_session_end}.get(ev, lambda _: None)(inp)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # a hook must never crash
        print(f"issue-writeback: {e}", file=sys.stderr)
    sys.exit(0)
