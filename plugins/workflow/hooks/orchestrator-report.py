#!/usr/bin/env python3
"""orchestrator-report: tells a session to report its PR / issue writes to the repo's orchestrator session.

PostToolUse. When a session creates or updates a PR, or writes to an issue, and the repository written to has exactly
one running session whose title starts with the orchestrator marker, inject `additionalContext` asking Claude to send
that session a one-line report with SendMessage. The orchestrator itself (same session id) gets nothing.

  - Writes detected: connector create_pull_request / update_pull_request / issue_write / add_issue_comment /
    sub_issue_write, and `gh pr create|edit`, `gh issue create|edit|comment|close`. The gh parsing reuses
    dev_flow_gate.py; the issue refs reuse issue-writeback.py. A create takes its number from the URL in the result;
    if no ref can be resolved, nothing is injected
  - The orchestrator: `claude agents --json` (running sessions only), the entry whose `name` starts with MARKER and
    whose cwd's `origin` remote is the GitHub repo written to (worktrees share their repo's origin; `gh -R` and
    connector writes to another repo go to that repo's orchestrator). Zero or several matches: nothing
  - Skipped in cloud sessions (CLAUDE_CODE_REMOTE=true) and Claude Projects sessions (CLAUDE_CODE_PROJECTS_SESSION=1)
  - At most once per PR / issue per session. State: <CLAUDE_PLUGIN_DATA or ~/.claude/state>/orchestrator-report/<session_id>.json

Whatever happens it never raises, always exits 0, and prints nothing when there is nothing to inject.
"""
import fcntl
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import dev_flow_gate as dfg  # gh parsing and tool-result helpers

    _spec = importlib.util.spec_from_file_location("issue_writeback", os.path.join(HERE, "issue-writeback.py"))
    iw = importlib.util.module_from_spec(_spec)  # issue refs from connector input, PR resolution
    _spec.loader.exec_module(iw)
except Exception:
    sys.exit(0)

MARKER = "\U0001F3AF"  # the orchestrator's title starts with this (e.g. "<marker> my-repo")
STATE_DIR = os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/.claude/state"),
                         "orchestrator-report")
GC_DAYS = 30
TAG = "[orchestrator-report]"
ISSUE_URL_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)")
GH_TRIGGERS = {("pr", "create"), ("pr", "edit"), ("issue", "create"), ("issue", "edit"),
               ("issue", "comment"), ("issue", "close")}
MCP_ERROR_RE = re.compile(r"\s*(MCP error|Error\b|failed\b)", re.I)
MCP_TRIGGERS = {"create_pull_request", "update_pull_request", "issue_write", "add_issue_comment", "sub_issue_write"}


# ------------------------------------------------------------------ targets
def _url_ref(rx, text):
    m = rx.search(text)
    return f"{m.group(1)}#{m.group(2)}" if m else None


def _num_ref(sel, repo, rx_kind):
    """`12`, `#12` or a URL of the given kind (pull / issues) -> owner/repo#12."""
    um = re.fullmatch(rf"https://github\.com/([\w.-]+/[\w.-]+)/{rx_kind}/(\d+)(?:[/?#].*)?", sel or "")
    if um:
        return f"{um.group(1)}#{um.group(2)}"
    nm = re.fullmatch(r"#?(\d+)", sel or "")
    return f"{repo}#{nm.group(1)}" if (nm and repo) else None


def targets_from_bash(cmd, cwd, tr):
    """[("PR" | "issue", "owner/repo#N")] for the gh writes in a Bash command that succeeded."""
    if not re.search(r"\bgh\b", cmd) or dfg.failed(tr):
        return []
    out_text = dfg.text_of(tr)
    calls = []
    for call in dfg.gh_commands(cmd, cwd):
        pos, opts = dfg.parse_args(call["args"])
        if len(pos) >= 2 and (pos[0], pos[1]) in GH_TRIGGERS:
            calls.append((call, pos, opts))
    # The output of one tool call holds every command's output. gh prints the created URL last, so the
    # N creates of a kind take the last N URLs of that kind, in order (a URL printed earlier is not taken)
    created = {}
    for kind, rx in (("pr", dfg.PR_URL_RE), ("issue", ISSUE_URL_RE)):
        n = sum(1 for _, p, _ in calls if p[0] == kind and p[1] == "create")
        urls = [f"{m.group(1)}#{m.group(2)}" for m in rx.finditer(out_text)]
        created[kind] = iter(urls[-n:] if n else [])
    out = []
    for call, pos, opts in calls:
        here = call["cwd"] or cwd
        repo = (dfg.opt(opts, "-R", "--repo") or call["env"].get("GH_REPO") or os.environ.get("GH_REPO")
                or (dfg.repo_from_cwd(here) if here else None))
        sel = pos[2] if len(pos) > 2 else None
        if pos[0] == "pr":
            if pos[1] == "create":
                ref = next(created["pr"], None)
            else:
                ref = _num_ref(sel, repo, "pull") or iw._resolve_pr(sel, repo, here, tr)
            out.append(("PR", ref))
        else:
            ref = next(created["issue"], None) if pos[1] == "create" else _num_ref(sel, repo, "issues")
            out.append(("issue", ref))
    return [(k, r) for k, r in out if r]


def targets_from_mcp(tool_name, ti, tr):
    b = dfg.base(tool_name)
    if b not in MCP_TRIGGERS:
        return []
    text = dfg.text_of(tr)
    if dfg.failed(tr) or MCP_ERROR_RE.match(text):
        return []  # the write failed; claiming the ref would also silence the report for a successful retry
    if dfg.FORM_RE.search(text):
        return []  # only an approval form was shown; nothing is written until the user submits it
    if b == "create_pull_request":
        ref = _url_ref(dfg.PR_URL_RE, text)
        return [("PR", ref)] if ref else []
    if b == "update_pull_request":
        o, r, n = ti.get("owner"), ti.get("repo"), ti.get("pullNumber") or ti.get("pull_number")
        try:
            return [("PR", f"{o}/{r}#{int(n)}")] if (o and r) else []
        except (TypeError, ValueError):
            return []
    if b == "issue_write" and ti.get("method") == "create":
        ref = _url_ref(ISSUE_URL_RE, text)
        return [("issue", ref)] if ref else []
    kind, ref = iw.refs_from_mcp(tool_name, ti)
    return [("issue", ref)] if kind == "write" else []


# ------------------------------------------------------------- orchestrator
def claude_bin():
    for p in (shutil.which("claude"), os.path.expanduser("~/.local/bin/claude"),
              os.path.expanduser("~/.claude/local/claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def running_sessions():
    exe = claude_bin()
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "agents", "--json"], capture_output=True, text=True, timeout=5)
        d = json.loads(r.stdout or "[]")
        return d if isinstance(d, list) else []
    except Exception:
        return []


def orchestrators_by_repo():
    """owner/repo (lowercase) -> the one running session titled with the marker whose folder's origin is that
    GitHub repo (worktrees share their repo's origin). A repo with several such sessions maps to None."""
    out = {}
    for s in running_sessions():
        if not isinstance(s, dict) or not (s.get("name") or "").startswith(MARKER) or not s.get("cwd"):
            continue
        repo = dfg.repo_from_cwd(s["cwd"])
        if repo:
            key = repo.lower()
            out[key] = None if key in out else s
    return out


# -------------------------------------------------------------------- state
def _path(session_id):
    return os.path.join(STATE_DIR, f"{session_id}.json")


def reported(session_id):
    try:
        with open(_path(session_id)) as f:
            return set(json.load(f).get("reported", []))
    except Exception:
        return set()


def claim(session_id, refs):
    """Record refs as reported and return the ones no other call had recorded yet.
    Read-check-write runs under flock, so parallel tool calls in one session never both claim a ref."""
    os.makedirs(STATE_DIR, exist_ok=True)
    gc()
    with open(_path(session_id) + ".lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        done = reported(session_id)
        new = [r for r in refs if r not in done]
        if new:
            tmp = _path(session_id) + f".{os.getpid()}.tmp"
            with open(tmp, "w") as f:
                json.dump({"reported": sorted(done | set(new))}, f)
            os.replace(tmp, _path(session_id))
        return new


def gc():
    try:
        cutoff = time.time() - GC_DAYS * 86400
        for n in os.listdir(STATE_DIR):
            fp = os.path.join(STATE_DIR, n)
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
    except Exception:
        pass


# --------------------------------------------------------------------- main
def url_of(kind, ref):
    repo, n = ref.rsplit("#", 1)
    return f"https://github.com/{repo}/{'pull' if kind == 'PR' else 'issues'}/{n}"


def on_post_tool_use(inp):
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true" or os.environ.get("CLAUDE_CODE_PROJECTS_SESSION") == "1":
        return None
    sid = inp["session_id"]
    tn = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    tr = inp.get("tool_response")
    cwd = inp.get("cwd")
    if tn == "Bash":
        found = targets_from_bash(ti.get("command", ""), cwd, tr)
    elif tn.startswith("mcp__"):
        found = targets_from_mcp(tn, ti, tr)
    else:
        return None
    seen = reported(sid)
    new = []
    for kind, ref in found:
        key = ref.lower()
        if key not in seen and key not in [k for _, _, k in new]:
            new.append((kind, ref, key))
    if not new:
        return None
    # Report to the orchestrator of the repository written to, which may differ from cwd's (gh -R, connector owner/repo)
    orchs = orchestrators_by_repo()
    to = {}  # orchestrator name -> [(kind, ref, key)]
    for kind, ref, key in new:
        orch = orchs.get(key.rsplit("#", 1)[0])
        if orch and orch.get("sessionId") != sid:
            to.setdefault(orch["name"], []).append((kind, ref, key))
    claimed = set(claim(sid, [k for items in to.values() for _, _, k in items])) if to else set()
    lines = []
    for name, items in to.items():
        items = [i for i in items if i[2] in claimed]
        if items:
            what = ", ".join(f"{kind} {ref} ({url_of(kind, ref)})" for kind, ref, _ in items)
            lines.append(f"Send `{name}` (the orchestrator session of that repository) a one-line report with"
                         f" SendMessage (to: `{name}`): what you did to which PR/issue, with its URL ({what}).")
    if not lines:
        return None
    return dfg.inject(
        f"{TAG} " + " ".join(lines) +
        " If you were started by that orchestrator (a linked child session), skip this: your turn-end notes"
        " already reach it. If the name is ambiguous, resolve it with ListAgents.")


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    if inp.get("hook_event_name") != "PostToolUse" or not inp.get("session_id"):
        return
    try:
        dfg.emit(on_post_tool_use(inp))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
