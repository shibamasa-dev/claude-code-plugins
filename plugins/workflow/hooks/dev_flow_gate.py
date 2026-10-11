#!/usr/bin/env python3
"""dev-flow-gate: a hook that stops the three steps of the dev-flow skill that cause accidents when skipped.

  - PreToolUse  (PR create): deny if the body lacks Closes / Refs (or `Refs: none (verbal request)`)
                             and an `Arch-Review:` line
  - PostToolUse (PR create): record the PR and the issues it Closes, and tell Claude the next step (waiting for review)
  - Stop                   : if this session created a PR but never started waiting for it (a PR event subscription
                             or a Monitor), block once per PR
  - PreToolUse  (merge)    : deny if there is no record that this session wrote (or read and confirmed) a
                             `## Result` section in the recorded Closes issues
  - PostToolUse (merge)    : after merging a PR with no record (created in another session), reply with a one-line reminder to check

It never reads GitHub on its own. It decides only from the tool calls in the session (name, input, result).
It looks at both the connector (mcp__*__create_pull_request etc.) and gh.
State lives in <CLAUDE_PLUGIN_DATA or ~/.claude/state>/dev-flow-gate/<session_id>.json.
Whatever happens it never raises and exits 0 (deny and block are the only outputs that stop anything).
"""
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime

STATE_DIR = os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/.claude/state"),
                         "dev-flow-gate")
GC_DAYS = 30
TAG = "[dev-flow-gate]"

CLOSE_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+((?:[\w.-]+/[\w.-]+)?#\d+)", re.I)
REFS_RE = re.compile(r"\brefs?\s*:?\s+(?:(?:[\w.-]+/[\w.-]+)?#\d+|none\s*\(verbal request\))", re.I)
# Whitespace within a line is [ \t]. With \s it would cross the newline and read the next line as the "reason"
ARCH_RE = re.compile(r"^[ \t]*Arch-Review:[ \t]*(?:not-needed|approved)[ \t]*[\u2014\u2013-]+[ \t]*\S", re.I | re.M)
# `## Result` and `## Notes for next time` are canonical. Older issues use the Japanese headings, which stay accepted
RESULT_RE = re.compile(r"^##[ \t]*(?:Results?|Notes for next time|結果|次回への引き継ぎ)[ \t]*$", re.M)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FENCE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", re.S | re.M)
# Heredoc: the rest of the <<[-]['"]DELIM['"] line (group 4), the body (group 5), the closing DELIM line
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)(\w+)\2([^\n]*)\n(.*?)\n[ \t]*\3[ \t]*(?=\n|$)", re.S)
HEREDOC_MARK_RE = re.compile(r"<<__HEREDOC_(\d+)__")
ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
# Wrappers that can precede gh, and their options that take a value (skipped so we can see the gh inside)
_WRAPPERS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "command": set(), "builtin": set(), "exec": {"-a"}, "nohup": set(), "time": set(),
    "nice": {"-n", "--adjustment"}, "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "-D", "--chdir"},
    "stdbuf": {"-i", "-o", "-e"},
}
_KEYWORDS = {"!", "{", "}", "if", "then", "else", "elif", "do", "while", "until", "time"}
PR_URL_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")


# ------------------------------------------------------------------ state io
def _path(session_id):
    return os.path.join(STATE_DIR, f"{session_id}.json")


class State:
    """Read-modify-write under flock. Safe when parallel tool calls arrive at the same time."""

    def __init__(self, session_id):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.p = _path(session_id)
        self.lock = self.p + ".lock"

    def __enter__(self):
        self.lf = open(self.lock, "w")
        fcntl.flock(self.lf, fcntl.LOCK_EX)
        try:
            with open(self.p) as f:
                self.d = json.load(f)
        except Exception:
            self.d = {}
        self.d.setdefault("prs", {})
        self.d.setdefault("results", [])
        return self

    def __exit__(self, *a):
        tmp = self.p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p)
        fcntl.flock(self.lf, fcntl.LOCK_UN)
        self.lf.close()


def read_state(session_id):
    try:
        with open(_path(session_id)) as f:
            d = json.load(f)
    except Exception:
        return {"prs": {}, "results": []}
    d.setdefault("prs", {})
    d.setdefault("results", [])
    return d


def now():
    return datetime.now().isoformat(timespec="seconds")


def gc():
    try:
        cutoff = time.time() - GC_DAYS * 86400
        for n in os.listdir(STATE_DIR):
            fp = os.path.join(STATE_DIR, n)
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
    except Exception:
        pass


# ------------------------------------------------------------------ helpers
def repo_from_cwd(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd or ".", "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=2)
        m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", r.stdout.strip())
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return None


def branch_from_cwd(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd or ".", "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=2)
        b = r.stdout.strip()
        return b if r.returncode == 0 and b and b != "HEAD" else None
    except Exception:
        return None


def norm_ref(ref, default_repo):
    """`#5` -> `owner/repo#5` (case-insensitive, like GitHub)."""
    if ref.startswith("#"):
        if not default_repo:
            return None
        ref = default_repo + ref
    return ref.lower()


def body_missing(body):
    """List of markers missing from the PR body. Text inside HTML comments (template instructions) does not count."""
    text = HTML_COMMENT_RE.sub("", body or "")
    missing = []
    if not (CLOSE_RE.search(text) or REFS_RE.search(text)):
        missing.append("`Closes #N` or `Refs #N` (`Refs: none (verbal request)` for a request with no issue)")
    if not ARCH_RE.search(text):
        missing.append("`Arch-Review: not-needed — <reason>` or `Arch-Review: approved — <where the GO is>`")
    return missing


def has_result(text):
    """Whether there is a `## Result` heading. Samples inside template HTML comments or code blocks do not count."""
    return bool(RESULT_RE.search(FENCE_RE.sub("", HTML_COMMENT_RE.sub("", text or ""))))


def closes_of(body, repo):
    text = HTML_COMMENT_RE.sub("", body or "")
    out = []
    for m in CLOSE_RE.finditer(text):
        r = norm_ref(m.group(1), repo)
        if r and r not in out:
            out.append(r)
    return out


def text_of(tr):
    """Flatten a tool result into one searchable string (also restores newlines inside JSON strings)."""
    if tr is None:
        return ""
    if isinstance(tr, str):
        try:
            tr = json.loads(tr)
        except Exception:
            return tr
    if isinstance(tr, dict) and isinstance(tr.get("stdout"), str):
        return tr["stdout"]
    parts = []

    def walk(x):
        if isinstance(x, str):
            # Connector results are often [{"type":"text","text":"<JSON>"}]. Open the inner JSON too and restore newlines
            if x[:1] in "{[":
                try:
                    walk(json.loads(x))
                    return
                except Exception:
                    pass
            parts.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(tr)
    return "\n".join(parts)


def failed(tr):
    """True if gh in Bash failed (we only record successes)."""
    if isinstance(tr, dict):
        if tr.get("interrupted") or tr.get("is_error"):
            return True
        err = tr.get("stderr") or ""
        if err and re.search(r"(?i)\b(error|failed|could not|HTTP [45]\d\d|GraphQL)\b", err):
            return True
    return False


# --------------------------------------------------------------- gh parsing
def split_heredocs(command):
    """Pull heredoc bodies out and leave only a `<<__HEREDOC_i__` marker in the command."""
    docs = []

    def repl(m):
        docs.append(m.group(5) + "\n")
        return f"<<__HEREDOC_{len(docs) - 1}__{m.group(4)}"
    return HEREDOC_RE.sub(repl, command), docs


def unwrap(c):
    """Strip leading assignments, keywords and wrappers from the tokens of one simple command. Returns (env, rest)."""
    env, i = {}, 0
    while i < len(c):
        t = c[i]
        m = ASSIGN_RE.match(t)
        if m:
            env[m.group(1)] = m.group(2)
            i += 1
        elif t in _KEYWORDS:
            i += 1
        elif os.path.basename(t) in _WRAPPERS:
            name, vopts = os.path.basename(t), _WRAPPERS[os.path.basename(t)]
            if name == "command" and i + 1 < len(c) and c[i + 1] in ("-v", "-V"):
                return env, []  # command -v gh only looks gh up, it does not run it
            i += 1
            while i < len(c) and c[i].startswith("-") and c[i] != "-":
                if c[i] == "--":
                    i += 1
                    break
                i += 2 if (c[i] in vopts and "=" not in c[i]) else 1
            if name == "timeout" and i < len(c) and re.fullmatch(r"[\d.]+[smhd]?", c[i]):
                i += 1  # the timeout duration
            if name == "nice" and i < len(c) and re.fullmatch(r"-?\d+", c[i]):
                i += 1
        else:
            break
    return env, c[i:]


def resolve_cd(args, cur):
    """Where `cd` goes. None when unknown (a variable, `cd -`, or a relative path from an unknown place)."""
    dests = [a for a in args if not (a.startswith("-") and a != "-")]
    if not dests:
        return os.path.expanduser("~")
    d = dests[0]
    if d == "-" or "$" in d or "`" in d:
        return None
    d = os.path.expanduser(d)
    if os.path.isabs(d):
        return os.path.normpath(d)
    return os.path.normpath(os.path.join(cur, d)) if cur else None


def gh_commands(command, cwd=None, _depth=0):
    """Return the gh calls in a Bash command as [{"args", "env", "stdin", "docs"}].

    Heredoc bodies are pulled out before lexing (so a ' or # in the body cannot break it). stdin is the index of the
    heredoc passed to that gh with `<<`. cwd is the directory that gh runs in (follows earlier `cd`s; None if unknown).
    Also looks through wrappers such as env, command and timeout, and inside `sh -c '...'`.
    A command that shlex cannot read yields nothing (lean towards not stopping, so symbols a PR body may contain don't misfire)."""
    command, docs = split_heredocs(command)
    command = command.replace("\\\n", " ")  # a trailing \ continues the line
    try:
        # A newline also separates commands (newlines inside quotes are kept)
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
        lex.whitespace = " \t\r"
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return []
    cmds, cur = [], []
    for t in toks:
        if t and set(t) <= set(";&|()\n"):
            cmds.append(cur)
            cur = []
        else:
            cur.append(t)
    cmds.append(cur)
    out, exported = [], {}
    for c in cmds:
        if c and c[0] in ("cd", "pushd"):
            cwd = resolve_cd(c[1:], cwd)
            continue
        if c and c[0] == "export":
            for t in c[1:]:
                m = ASSIGN_RE.match(t)
                if m:
                    exported[m.group(1)] = m.group(2)
            continue
        env, rest = unwrap(c)
        if not rest:
            exported.update(env)  # a line with only `A=B` sets a shell variable (passed to children if the name was exported)
            continue
        env = {**exported, **env}
        exe = os.path.basename(rest[0])
        if exe in ("sh", "bash", "zsh", "dash") and "-c" in rest[1:] and _depth < 3:
            k = rest.index("-c")
            if k + 1 < len(rest):
                for call in gh_commands(rest[k + 1], cwd, _depth + 1):
                    call["env"] = {**env, **call["env"]}
                    out.append(call)
            continue
        if exe != "gh":
            continue
        stdin, args = None, []
        for a in rest[1:]:
            m = HEREDOC_MARK_RE.fullmatch(a)
            if m:
                stdin = int(m.group(1))
            else:
                args.append(a)
        out.append({"args": args, "env": env, "stdin": stdin, "docs": docs, "cwd": cwd})
    return out


# gh options that take a value (listed so we can skip them; we only pick up the values we need)
_VALUE_OPTS = {
    "-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--title", "-H", "--head", "-B", "--base",
    "-T", "--template", "-a", "--assignee", "-l", "--label", "-m", "--milestone", "-p", "--project",
    "-r", "--reviewer", "--recover", "-A", "--author-email", "--subject", "--match-head-commit",
    "--add-label", "--remove-label", "--add-assignee", "--remove-assignee", "--add-project",
    "--remove-project", "--attach",
}


def parse_args(args):
    """(positional, opts). opts keeps the last value (including the `--x=v` form)."""
    pos, opts, i = [], {}, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a.startswith("--") and "=" in a:
            k, v = a.split("=", 1)
            opts[k] = v
        elif a in _VALUE_OPTS:
            opts[a] = args[i + 1] if i + 1 < len(args) else ""
            i += 1
        elif a.startswith("-") and len(a) > 2 and a[:2] in _VALUE_OPTS and not a.startswith("--"):
            opts[a[:2]] = a[2:]  # the -Ro/r form
        elif a.startswith("-") and len(a) > 1:
            opts[a] = True
        else:
            pos.append(a)
        i += 1
    return pos, opts


def opt(opts, *names):
    for n in names:
        if n in opts and opts[n] is not True:
            return opts[n]
    return None


def read_file(path, cwd):
    if not path or path == "-":
        return None
    p = path if os.path.isabs(path) else os.path.join(cwd or ".", path)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def gh_body(opts, cwd, call):
    """The body passed to gh. None when it was passed in a way we cannot check (a variable, piped stdin, --fill, ...)."""
    docs = call["docs"]
    b = opt(opts, "-b", "--body")
    if b is not None:
        m = HEREDOC_MARK_RE.search(b)
        if m:
            return docs[int(m.group(1))]  # --body "$(cat <<'EOF' ... EOF)". Only that heredoc's body
        # A body that is just a variable such as "$BODY" cannot be inspected
        return None if re.fullmatch(r"\s*\$\{?\w+\}?\s*", b) else b
    f = opt(opts, "-F", "--body-file")
    if f in ("-", "/dev/stdin"):
        # `-F - <<'EOF'`. Only look at the heredoc passed to this gh (a pipe and the like cannot be checked)
        return docs[call["stdin"]] if call["stdin"] is not None else None
    return read_file(f, cwd)


def gh_calls(command, cwd):
    """[(kind, info)] kind is one of pr_create / pr_merge / issue_edit / issue_view

    The repo is resolved in the same order as gh: -R -> GH_REPO set before this gh -> inherited GH_REPO -> origin of the directory gh runs in."""
    out = []
    for call in gh_commands(command, cwd):
        pos, opts = parse_args(call["args"])
        if len(pos) < 2:
            continue
        here = call["cwd"]
        repo = (opt(opts, "-R", "--repo") or call["env"].get("GH_REPO") or os.environ.get("GH_REPO")
                or (repo_from_cwd(here) if here else None))
        if pos[0] == "pr" and pos[1] == "create":
            out.append(("pr_create", {"repo": repo, "body": gh_body(opts, here or cwd, call),
                                      "head": opt(opts, "-H", "--head") or (branch_from_cwd(here) if here else None)}))
        elif pos[0] == "pr" and pos[1] == "merge":
            out.append(("pr_merge", {"repo": repo, "selector": pos[2] if len(pos) > 2 else None, "cwd": here}))
        elif pos[0] == "issue" and pos[1] in ("edit", "view") and len(pos) > 2:
            sel = pos[2]
            um = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)", sel)
            if um:
                ref = f"{um.group(1)}#{um.group(2)}".lower()
            else:
                nm = re.fullmatch(r"#?(\d+)", sel)
                ref = f"{repo}#{nm.group(1)}".lower() if (nm and repo) else None
            if ref:
                out.append(("issue_" + pos[1], {"ref": ref, "body": gh_body(opts, here or cwd, call)}))
    return out


def merge_refs_from_gh(info, st_prs):
    """Candidate PRs that gh pr merge points at. A bare number with no resolvable repo matches every recorded PR with that number."""
    sel = info.get("selector")
    um = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)(?:[/?#].*)?", sel or "")
    if um:
        return [f"{um.group(1)}#{um.group(2)}".lower()]
    repo = (info.get("repo") or "").lower() or None
    nm = re.fullmatch(r"#?(\d+)", sel or "")
    if nm:
        if repo:
            return [f"{repo}#{nm.group(1)}"]
        return [ref for ref in st_prs if ref.endswith("#" + nm.group(1))]
    head = sel or (branch_from_cwd(info["cwd"]) if info.get("cwd") else None)
    return [ref for ref, pr in st_prs.items()
            if head and pr.get("head") == head and (not repo or ref.startswith(repo + "#"))]


FORM_RE = re.compile(r"(?i)interactive form|form has been shown|waiting for the user|pending (?:user )?(?:approval|confirmation)")


# Ways a Monitor command can name a PR. A bare number (sleep 30 and the like) does not count
MONITOR_PR_RE = re.compile(
    r"(?:pulls?|issues)/(?P<n>\d+)(?!\d)"
    r"|(?<![\w&])#(?P<n2>\d+)(?!\d)"
    r"|\bpr\s+(?:view|checks|status|diff|comment|review|merge|ready|edit)\b(?P<args>[^;&|\n]*)"
    r"|\b(?:pullnumber|pull_number|pr_number)\W{0,3}(?P<n3>\d+)"
    r"|\bfor\s+\w+\s+in\b(?P<list>[^;\n]*)")
VALUE_FLAG_RE = re.compile(r"(?:^|\s)(?:-i|--interval|-l|--limit|-q|--jq|-t|--template|--json)(?:[\s=]+\S+)")


def wait_targets(tool_name, tool_input, prs):
    """Refs of PRs whose wait has started. A subscription covers only that PR; a Monitor covers only the PRs whose number (and repo) appear in its command."""
    if tool_name != "Monitor":
        o, r = tool_input.get("owner"), tool_input.get("repo")
        n = tool_input.get("pullNumber") or tool_input.get("pull_number") or tool_input.get("pr_number")
        if isinstance(r, str) and "/" in r and not o:
            o, r = r.split("/", 1)
        try:
            ref = f"{o}/{r}#{int(n)}".lower()
        except (TypeError, ValueError):
            return []
        return [ref] if ref in prs else []
    text = json.dumps(tool_input, ensure_ascii=False).lower().replace("\\n", "\n")
    names_repo = re.search(r"repos/|github\.com/|\s(?:-r|--repo)[\s=]", text)
    nums = set()
    for m in MONITOR_PR_RE.finditer(text):
        if m.group("list") is not None:
            nums.update(re.findall(r"(?<![\w.$-])(\d+)(?![\w.])", m.group("list")))
        elif m.group("args") is not None:
            args = VALUE_FLAG_RE.sub(" ", m.group("args"))
            nums.update(re.findall(r"(?<![\w./$-])(\d+)(?![\w./])", args))
        else:
            nums.add(m.group("n") or m.group("n2") or m.group("n3"))
    out = []
    for n in nums:
        cands = [ref for ref in prs if ref.rsplit("#", 1)[1] == n]
        named = [ref for ref in cands if ref.rsplit("#", 1)[0] in text]
        if named:
            out += named
        elif not names_repo and len(cands) == 1:
            out += cands
    return sorted(set(out))


def base(tool_name):
    return tool_name.rsplit("__", 1)[-1] if tool_name.startswith("mcp__") else tool_name


# ------------------------------------------------------------------ outputs
def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def inject(context):
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}


def emit(obj):
    if obj:
        print(json.dumps(obj, ensure_ascii=False))


NEXT_STEP = (f"{TAG} PR created. Next, wait for review and CI (dev-flow step 5; the procedure is in pr-review-triage). "
             "In a cloud session subscribe to PR events (subscribe_pr_activity); locally start a Monitor. "
             "Before merging, write `## Result` in the body of each issue the PR Closes.")


# ------------------------------------------------------------------- events
def pre_create_check(body):
    if body is None:
        return deny(f"{TAG} Cannot check the PR body. Pass the body with --body or --body-file "
                    "(--fill, --editor, --web, a variable, or stdin other than a heredoc cannot be checked).")
    missing = body_missing(body)
    if missing:
        return deny(f"{TAG} The PR body is missing these lines (dev-flow step 4):\n- " + "\n- ".join(missing)
                    + "\nAdd them and create the PR again.")
    return None


def pre_merge_check(ref, st):
    pr = st["prs"].get(ref)
    if not pr:
        return None  # we cannot know about another session's PR. PostToolUse replies with a reminder
    missing = [i for i in pr.get("closes", []) if i not in st["results"]]
    if not missing:
        return None
    return deny(f"{TAG} {ref} Closes {', '.join(missing)}, but this session has no record of writing or confirming"
                " `## Result` in that issue's body (dev-flow step 7)."
                " Merging would auto-close it with nothing recorded. Get the current body with issue_read,"
                " append `## Result`, write it back with issue_write (update), then merge."
                " If it is already there, reading it again with issue_read lets the merge through.")


def on_pre_tool_use(inp):
    tn = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    cwd = inp.get("cwd")
    b = base(tn)
    if tn.startswith("mcp__") and b == "create_pull_request":
        return pre_create_check(ti.get("body") or "")
    if tn.startswith("mcp__") and b in ("merge_pull_request", "enable_pr_auto_merge"):
        o, r, n = ti.get("owner"), ti.get("repo"), ti.get("pullNumber") or ti.get("pull_number")
        if not (o and r and n):
            return None
        return pre_merge_check(f"{o}/{r}#{int(n)}".lower(), read_state(inp["session_id"]))
    if tn == "Bash":
        cmd = ti.get("command", "")
        if not re.search(r"\bgh\b", cmd):
            return None
        st = None
        for kind, info in gh_calls(cmd, cwd):
            if kind == "pr_create":
                res = pre_create_check(info["body"])
                if res:
                    return res
            elif kind == "pr_merge":
                st = st or read_state(inp["session_id"])
                for ref in merge_refs_from_gh(info, st["prs"]):
                    res = pre_merge_check(ref, st)
                    if res:
                        return res
    return None


def record_pr(st, ref, body, head):
    repo = ref.split("#", 1)[0]
    st.d["prs"][ref] = {"closes": closes_of(body, repo), "head": head, "created_at": now(),
                        "wait_started": False, "nagged": False}


def on_post_tool_use(inp):
    tn = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    tr = inp.get("tool_response")
    cwd = inp.get("cwd")
    b = base(tn)
    sid = inp["session_id"]

    if tn == "Monitor" or (tn.startswith("mcp__") and b == "subscribe_pr_activity"):
        if os.path.exists(_path(sid)):
            with State(sid) as st:
                for ref in wait_targets(tn, ti, st.d["prs"]):
                    st.d["prs"][ref]["wait_started"] = True
        return None

    if tn.startswith("mcp__") and b == "create_pull_request":
        m = PR_URL_RE.search(text_of(tr))
        if not m:
            return None
        with State(sid) as st:
            record_pr(st, f"{m.group(1)}#{m.group(2)}".lower(), ti.get("body") or "", ti.get("head"))
        return inject(NEXT_STEP)

    if tn.startswith("mcp__") and b in ("issue_write", "issue_read"):
        o, r, n = ti.get("owner"), ti.get("repo"), ti.get("issue_number")
        if not (o and r and n):
            return None
        if b == "issue_write":
            # Merely showing an approval form (nothing is updated until the user submits it) is not a write.
            # Count it only when the result returns that issue's URL (otherwise, reading it again with issue_read lets it through)
            done = re.search(rf"/issues/{int(n)}(?!\d)", text_of(tr)) and not FORM_RE.search(text_of(tr))
            text = (ti.get("body") or "") if ti.get("method") == "update" and done else ""
        else:
            text = text_of(tr) if ti.get("method", "get") == "get" else ""
        if has_result(text):
            with State(sid) as st:
                ref = f"{o}/{r}#{int(n)}".lower()
                if ref not in st.d["results"]:
                    st.d["results"].append(ref)
        return None

    if tn.startswith("mcp__") and b in ("merge_pull_request", "enable_pr_auto_merge"):
        o, r, n = ti.get("owner"), ti.get("repo"), ti.get("pullNumber") or ti.get("pull_number")
        if o and r and n and f"{o}/{r}#{int(n)}".lower() not in read_state(sid)["prs"]:
            return inject(f"{TAG} Merged a PR that this session did not create. Check that each issue it Closes"
                          " has `## Result`, and write it if missing (dev-flow step 7).")
        return None

    if tn == "Bash":
        cmd = ti.get("command", "")
        if not re.search(r"\bgh\b", cmd) or failed(tr):
            return None
        out = None
        for kind, info in gh_calls(cmd, cwd):
            if kind == "pr_create":
                m = PR_URL_RE.search(text_of(tr))
                if m:
                    with State(sid) as st:
                        record_pr(st, f"{m.group(1)}#{m.group(2)}".lower(), info["body"] or "", info["head"])
                    out = inject(NEXT_STEP)
            elif kind in ("issue_edit", "issue_view"):
                if kind == "issue_edit":
                    # gh issue edit prints the issue URL on success
                    num = info["ref"].rsplit("#", 1)[1]
                    text = info["body"] if re.search(rf"/issues/{num}(?!\d)", text_of(tr)) else ""
                else:
                    text = text_of(tr)
                if has_result(text):
                    with State(sid) as st:
                        if info["ref"] not in st.d["results"]:
                            st.d["results"].append(info["ref"])
            elif kind == "pr_merge":
                st = read_state(sid)
                if not any(r in st["prs"] for r in merge_refs_from_gh(info, st["prs"])):
                    out = inject(f"{TAG} Merged a PR that this session did not create. Check that each issue it Closes"
                                 " has `## Result`, and write it if missing (dev-flow step 7).")
        return out
    return None


def on_stop(inp):
    if inp.get("stop_hook_active"):
        return None
    sid = inp["session_id"]
    if not os.path.exists(_path(sid)):
        return None
    due = []
    with State(sid) as st:
        for ref, pr in st.d["prs"].items():
            if not pr.get("wait_started") and not pr.get("nagged"):
                pr["nagged"] = True
                due.append(ref)
    if not due:
        return None
    reason = (f"{TAG} Created {', '.join(due)} but has not started waiting for review and CI (dev-flow step 5)."
              " In a cloud session, subscribe to PR events with subscribe_pr_activity before ending the turn."
              " Locally, start a Monitor following pr-review-triage."
              " If there is a reason not to wait (e.g. the user said it is unnecessary), say so in your reply and end"
              " the turn (this PR will not be stopped again).")
    return {"decision": "block", "reason": reason}


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    ev = inp.get("hook_event_name", "")
    if not inp.get("session_id"):
        return
    try:
        if ev == "PreToolUse":
            emit(on_pre_tool_use(inp))
        elif ev == "PostToolUse":
            emit(on_post_tool_use(inp))
        elif ev == "Stop":
            emit(on_stop(inp))
        elif ev == "SessionStart":
            gc()
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
