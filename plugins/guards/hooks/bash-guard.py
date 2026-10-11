#!/usr/bin/env python3
"""PreToolUse hook: a generic guard dispatcher for Bash commands.

The matcher is "Bash" (it can only match tool names), so this runs on every Bash call
and the RULES in this script filter on the command itself. Adding a rule = write one
function and register it in RULES (no extra hook registration).

Current rules:
  (merge-gate was removed on 2026-10-06. Merge decisions moved to the workflow plugin's
   dev-flow skill and dev-flow-gate hook. Auto-merge is configured in the repo's .claude/dev-flow.json)
  1. rm-guard    : prevents destructive accidents with recursive rm (-r/-rf).
                   - Catastrophic targets (/, ~, $HOME, system dirs, bare *, etc.) → always deny
                   - Relative paths / /tmp / $TMPDIR / under the configured worktree_dirs → allow
                   - Root of a merged, clean linked worktree → allow (wherever it lives)
                   - Anything else (absolute paths, unresolvable variable expansions) → deny
                   - `trash` (macOS move-to-Trash) is allowed except for catastrophic targets. It can be
                     undone, so Claude can finish a cleanup the user approved (approved 2026-10-03).
                     Unmerged worktrees are stopped by worktree-guard (wherever they live)
                   **There is no bypass marker** (removed 2026-09-23). The point is to make a
                   human confirm; if Claude could pass by self-declaration, no confirmation would happen.
                   Simple variable assignments within the same command (`T=/tmp/x; rm -rf $T`)
                   are resolved before judging (fewer false positives, as far as they resolve).
                   Wrappers such as sudo/env/command/nohup/xargs, `sh -c`, eval, ( ), $( ),
                   and `find -delete`/`-exec rm` are expanded and judged the same way (2026-10-04).
                   Values of wrappers' long options and short-option bundles are skipped too. A find
                   without a start path starts from the current directory, and an unfiltered
                   `find . -delete` is treated like `rm -rf .` (2026-10-06).
  2. push-freshness : before git push, verify the branch is not behind origin/<default branch>.
                   The default branch is origin/HEAD (else origin/main or origin/master).
                   Makes branches cut from a stale default branch (e.g. by spinoffs) catch up,
                   so merge+test catches semantic drift (signature changes, etc.), not just
                   text conflicts. Passes if fetch fails (offline), on the default branch, or
                   behind=0. Denies only when behind>0.
                   **There is no bypass marker** (removed 2026-09-22). The hook recomputes
                   behind itself, so there is no need to trust a claim of "merged it in".
                   With the marker, Claude could pass with zero verification just by adding a string.
"""
import fnmatch
import glob
import itertools
import json
import os
import re
import shlex
import subprocess
import sys

# cwd of the Bash call being checked (set from the hook input in main). Used by the git rules.
_CWD = None

HOME = os.path.normpath(os.path.expanduser("~"))   # so a trailing / or // in $HOME doesn't break prefix checks

SYSTEM_DIRS = {
    "/etc", "/usr", "/var", "/bin", "/sbin", "/opt",
    "/Library", "/System", "/Applications", "/Users", "/private",
}


def _option_dirs(key: str) -> tuple:
    """Folders listed in the plugin settings (userConfig). Claude Code passes them to hooks as
    CLAUDE_PLUGIN_OPTION_<KEY> (comma-separated, `~` allowed). () if empty.
    Root, home and system dirs are not accepted as locations (they would all become "safe")."""
    out = []
    for part in os.environ.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "").split(","):
        part = os.path.expandvars(os.path.expanduser(part.strip()))
        if not part or not os.path.isabs(part):
            continue
        d = os.path.normpath(part)
        if d in ("/", HOME) or d in SYSTEM_DIRS:
            continue
        out.append(d)
    return tuple(dict.fromkeys(out))


# Folders that hold worktrees (setting worktree_dirs; empty by default)
WORKTREE_DIRS = _option_dirs("worktree_dirs")

SAFE_PREFIXES = ("/tmp/", "/private/tmp/") + tuple(d + "/" for d in WORKTREE_DIRS)
SAFE_VAR_PREFIXES = ("$TMPDIR", "${TMPDIR")


def deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def ask(reason: str) -> dict:
    """Make Claude Code ask the user for permission. Unlike deny, the user can allow it on the spot."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


# ------------------------------------------------------------------ rm-guard
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _strip_heredocs(command: str) -> str:
    """Drop heredoc bodies. A body is data (an issue body, SQL, etc.), not commands."""
    out, pending = [], []
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        out.append(line)
        pending.extend(m.group(2) for m in HEREDOC_RE.finditer(line))
    return "\n".join(out)


SUBST = "$__SUBST__"   # marker left in the outer segment for a command substitution (treated as an unresolvable variable)


def _parse_segments(command: str) -> list:
    """Split a command into segments, one per simple command.

    Returns a list of dict(text, depth, before, after). before/after are the surrounding separators
    ('^' start, '$' end, ';' '&&' '||' '|' '&' '\\n' '(' ')').
    - Don't split inside quotes (the contents are data). But `$( )` and backquotes run even
      inside double quotes, so their contents become a separate segment (depth+1)
    - `( )` outside quotes is a subshell; its contents also become a separate segment (depth+1)
    - The & in `2>&1` and `&>` is not a separator
    """
    s = _strip_heredocs(command)
    out = []
    st = {"buf": [], "before": "^", "depth": 0, "quote": None}
    stack = []   # (closer, outer state)

    def flush(sep):
        out.append({"text": "".join(st["buf"]), "depth": st["depth"],
                    "before": st["before"], "after": sep})
        st["buf"] = []
        st["before"] = sep

    def open_subst(closer):
        stack.append((closer, dict(st, buf=list(st["buf"]))))
        st.update(buf=[], before="(", depth=st["depth"] + 1, quote=None)

    def close_subst():
        flush(")")
        closer, outer = stack.pop()
        st.update(outer)
        if closer != "(":           # $( ) / ` ` leave a marker as part of the outer word
            st["buf"].append(SUBST)
        else:
            st["before"] = ")"

    i = 0
    while i < len(s):
        c = s[i]
        q = st["quote"]
        top = stack[-1][0] if stack else None
        if q == "'":
            st["buf"].append(c)
            if c == "'":
                st["quote"] = None
            i += 1
            continue
        if c == "\\" and i + 1 < len(s):
            st["buf"].append(s[i:i + 2]); i += 2
            continue
        if top == "`" and c == "`":
            close_subst(); i += 1
            continue
        if s.startswith("$(", i):
            open_subst(")"); i += 2
            continue
        if c == "`":
            open_subst("`"); i += 1
            continue
        if q == '"':
            st["buf"].append(c)
            if c == '"':
                st["quote"] = None
            i += 1
            continue
        if c in "'\"":
            st["quote"] = c; st["buf"].append(c); i += 1
            continue
        if c == ")":
            if top in (")", "("):
                close_subst()
            else:
                flush(")")          # case patterns etc. Treat as a separator
            i += 1
            continue
        if c == "(" and st["buf"] and st["buf"][-1] in "?*+@!":
            # extglob (`@(a|b)` etc.) is part of the word. Don't split on the `|` inside
            j, d = i, 0
            while j < len(s):
                d += {"(": 1, ")": -1}.get(s[j], 0)
                j += 1
                if d == 0:
                    break
            st["buf"].append(s[i:j]); i = j
            continue
        if c == "(":
            flush("(")
            stack.append(("(", dict(st, buf=[])))
            st.update(buf=[], before="(", depth=st["depth"] + 1)
            i += 1
            continue
        two = s[i:i + 2]
        if two in ("&&", "||", "|&", ";;"):
            flush(two); i += 2
            continue
        if c == "&" and (s[i + 1:i + 2] == ">" or (i > 0 and s[i - 1] in "<>")):
            st["buf"].append(c); i += 1   # redirection (2>&1 / &>)
            continue
        if c in "|;&\n":
            flush(c); i += 1
            continue
        st["buf"].append(c)
        i += 1
    flush("$")
    while stack:                      # unclosed parentheses: still evaluate the rest of the outer levels
        _, outer = stack.pop()
        st.update(outer)
        flush("$")
    return out


def _split_segments(command: str):
    """List of text pieces split on pipes, semicolons, &&, newlines, subshells and command substitutions."""
    return [seg["text"] for seg in _parse_segments(command)]


# Only `$NAME` and `${NAME}`. Expansions with operators such as `${NAME:-word}` are not resolved (the $ stays = undecidable).
# Previously only the `${NAME` part was replaced, leaving `:-/}`, so `T=; rm -rf ${T:-/}` looked like a relative path
VAR_REF_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
ASSIGN_TOKEN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)


def _resolve(raw: str, assigns: dict) -> str:
    """Expand only known assignments. Unknown variables stay as they are (= falls to other)."""
    if not assigns:
        return raw

    def sub(m):
        v = assigns.get(m.group(1) or m.group(2))
        return v if v is not None else m.group(0)
    return VAR_REF_RE.sub(sub, raw)


def _resolved_value(raw: str, assigns: dict):
    """Statically resolve the right-hand side of an assignment. None if it can't be resolved (= the variable is unknown from then on)."""
    v = _resolve(raw, assigns)
    if "$" in v or "`" in v:
        return None
    return os.path.expanduser(v) if v.startswith("~") else v


# ------------------------------------------ enumerating simple commands (shared by all rules)
# Wrappers that just hand execution to another command. Skip them and evaluate the inner command.
# For options that take a value, skip the next token too.
_WRAPPER_OPTS_WITH_VALUE = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-r", "-t", "-T", "-U",
             "--user", "--group", "--host", "--prompt", "--close-from", "--chdir", "--chroot",
             "--role", "--type", "--command-timeout", "--other-user"},
    "doas": {"-u", "-C"},
    "nice": {"-n", "--adjustment"},
    "exec": {"-a"},
    "time": set(),
    "nohup": set(),
    "command": set(),
    "builtin": set(),
    "caffeinate": {"-t", "-w"},
    "stdbuf": {"-i", "-o", "-e"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "gtimeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-n", "-P", "-L", "-s", "-E", "-d", "-a", "--max-args", "--max-procs",
              "--max-lines", "--max-chars", "--eof", "--delimiter", "--arg-file", "--replace"},
}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}


def _short_valued(a: str, with_val: set):
    """Read a short-option bundle (`-nu root` / `-uroot`) the way getopt does.
    returns (the letter that takes a value, the value attached to the bundle or None). (None, None) if no letter takes a value."""
    for j, c in enumerate(a[1:], 1):
        if "-" + c in with_val:
            return c, (a[j + 1:] or None)
    return None, None


def _takes_next(a: str, with_val: set) -> bool:
    """Whether option a takes the next token as its value.

    Handles the long form `--user root` and a value-taking short option at the end of a bundle
    such as `-nu root`. Missing these turns the value into the command (`sudo --user root rm -rf /`
    became `root rm -rf /` and slipped past the guard)."""
    if a.startswith("--"):
        return "=" not in a and a in with_val
    c, attached = _short_valued(a, with_val)
    return c is not None and attached is None
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "fi", "done", "coproc"}


def _unwrap(tokens: list):
    """Strip wrappers. returns (env, tokens, nested, flags)

    env    : environment variable assignments at the start (and within wrappers)
    tokens : the command actually executed (empty = assignments only, or the contents are in nested)
    nested : strings from `sh -c STR` / `eval ...` / `env -S STR` (evaluated recursively)
    flags  : {'xargs': arguments come from stdin, 'shell_state': may change the current shell's
              cwd/variables like eval/source, 'chdir': env -C changes the cwd}
    """
    env, nested, flags = {}, [], {"xargs": False, "shell_state": False, "chdir": False}
    t = list(tokens)
    while t:
        while t and t[-1] == "}":
            t.pop()
        if not t:
            break
        h = t[0]
        m = ASSIGN_TOKEN_RE.match(h)
        if m:
            env[m.group(1)] = m.group(2)
            t.pop(0)
            continue
        if h in _KEYWORDS:
            t.pop(0)
            continue
        b = os.path.basename(h)
        if b in ("command", "builtin") and len(t) > 1 and t[1] in ("-v", "-V"):
            break   # a lookup, not an execution
        if b == "env":
            t.pop(0)
            while t:
                a = t[0]
                if ASSIGN_TOKEN_RE.match(a):
                    k, v = a.split("=", 1); env[k] = v; t.pop(0)
                    continue
                if a == "--":
                    t.pop(0)
                    break
                if not a.startswith("-") or a == "-":
                    if a == "-":    # `env -` is the same as -i
                        t.pop(0)
                        continue
                    break
                t.pop(0)
                if a.startswith("--"):
                    name, eq, attached = a.partition("=")
                    opt = {"--unset": "u", "--chdir": "C", "--split-string": "S"}.get(name)
                    attached = attached if eq else None
                else:   # also read bundles like `-iu FOO`
                    opt, attached = _short_valued(a, {"-u", "-C", "-S"})
                if opt is None:
                    continue
                val = attached if attached is not None else (t.pop(0) if t else "")
                if opt == "C":
                    flags["chdir"] = True
                elif opt == "S":
                    try:
                        t = shlex.split(val) + t
                    except ValueError:
                        nested.append(val); t = []
                    break
            continue
        if b in _WRAPPER_OPTS_WITH_VALUE:
            with_val = _WRAPPER_OPTS_WITH_VALUE[b]
            if b == "xargs":
                flags["xargs"] = True
            t.pop(0)
            while t and t[0].startswith("-") and t[0] != "-":
                a = t.pop(0)
                if a == "--":
                    break
                if b == "sudo" and (a.startswith("--chdir") or
                                    (not a.startswith("--") and _short_valued(a, with_val)[0] == "D")):
                    flags["chdir"] = True   # sudo -D/--chdir DIR changes the cwd
                if _takes_next(a, with_val) and t:
                    t.pop(0)
            if b in ("timeout", "gtimeout") and t:
                t.pop(0)   # DURATION
            while b == "sudo" and t and ASSIGN_TOKEN_RE.match(t[0]):
                k, v = t.pop(0).split("=", 1); env[k] = v
            continue
        if b in _SHELLS:
            for j in range(1, len(t)):
                a = t[j]
                if not a.startswith("-"):
                    break
                if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a):
                    if j + 1 < len(t):
                        nested.append(t[j + 1])
                    t = []
                    break
            break
        if b == "eval":
            nested.append(" ".join(t[1:]))
            flags["shell_state"] = True
            t = []
            break
        if b in ("source", "."):
            flags["shell_state"] = True
        break
    return env, t, nested, flags


def _certain(seg: dict) -> bool:
    """Whether this segment is certain to run in the current shell (so a cd or assignment affects what follows).

    A cd or assignment inside a subshell, conditional (`a && cd x` / `a || cd x`), pipe or
    background job does not necessarily affect what follows."""
    return (seg["depth"] == 0 and seg["before"] in ("^", ";", "\n", "&", ";;")
            and seg["after"] not in ("|", "|&", "&"))


def _resolve_cd(tokens: list, cur, assigns: dict):
    """Destination of `cd [-L|-P] [dir]`. None if undecidable."""
    args = [a for a in tokens[1:] if a not in ("-L", "-P", "-e", "-@")]
    if not args:
        return HOME
    if len(args) > 1 or args[0] == "-":
        return None
    v = _resolved_value(args[0], assigns)
    if v is None:
        return None
    if not os.path.isabs(v):
        # with CDPATH set, a relative name may go somewhere else
        if cur is None or (os.environ.get("CDPATH") and not v.startswith(".")):
            return None
        v = os.path.join(cur, v)
    v = os.path.normpath(v)
    return v if os.path.isdir(v) else None


class Cmd:
    """One enumerated simple command. cwd is the directory it runs in (None if undecidable)."""
    __slots__ = ("env", "tokens", "cwd", "raw", "opaque", "xargs", "assigns")

    def __init__(self, env, tokens, cwd, raw, opaque, xargs, assigns):
        self.env, self.tokens, self.cwd, self.raw = env, tokens, cwd, raw
        self.opaque, self.xargs, self.assigns = opaque, xargs, assigns


_CMDS_CACHE = {}


def _commands(command: str) -> list:
    """Enumerate the simple commands in command, expanding wrappers, `sh -c`, eval, subshells
    and command substitutions (shared by all rules; memoized)."""
    key = (command, _CWD)
    if key not in _CMDS_CACHE:
        start = _CWD if (_CWD and os.path.isdir(_CWD)) else None
        _CMDS_CACHE[key] = list(_walk(command, start, {}, 0))
    return _CMDS_CACHE[key]


def _walk(command: str, cwd, assigns: dict, level: int):
    if level > 4:
        yield Cmd({}, [], None, command, True, False, {})
        return
    cur, assigns = cwd, dict(assigns)
    funcs = False   # a function was defined (cd etc. may be overridden)
    compound = 0    # inside if/while/until/for/select/case (a cd or assignment inside may not run)
    for seg in _parse_segments(command):
        text = seg["text"].strip()
        if not text:
            continue
        try:
            raw_tokens = shlex.split(text)
            opaque = False
        except ValueError:
            raw_tokens = text.split()
            opaque = True
        if (seg["after"] == "(" and len(raw_tokens) == 1) or raw_tokens[:1] == ["function"]:
            # A function definition (`cd() { :; }` / `function cd {…}`). cd etc. may mean something else
            # from here on, so the cwd becomes undecidable (the body is evaluated as the following segments)
            cur, funcs = None, True
            assigns = {k: None for k in assigns}
            continue
        head = raw_tokens[0] if raw_tokens else ""
        if head in ("if", "while", "until", "for", "select", "case"):
            compound += 1   # a cd in the condition may fail too, so uncertainty starts at the opening line
        env, tokens, nested, flags = _unwrap(raw_tokens)
        certain = _certain(seg) and compound == 0
        b = os.path.basename(tokens[0]) if tokens else ""
        here = None if flags["chdir"] else cur
        yield Cmd(env, tokens, here, text, opaque, flags["xargs"], dict(assigns))
        # `sh -c` etc. run in a child shell, which doesn't see unexported variables (in
        # `X=/tmp/a; bash -c 'rm -rf $X/*'`, $X is empty). Whether it was exported can't be decided
        # statically, so mark them unknown. eval runs in the current shell
        child = assigns if flags["shell_state"] else {k: None for k in assigns}
        for n in nested:
            yield from _walk(n, here, child, level + 1)
        if b == "find":
            # Also evaluate the command inside `-exec rm <path> ;` as a simple command (looking only at
            # the start path misses actions that delete paths unrelated to it). `{}` is an entry found
            # under the start path, which the start-path check covers, so it stays a relative name
            for action in _find_action_cmds(tokens):
                yield from _walk(shlex.join(action), here, assigns, level + 1)
        # ---- how this segment changes the current shell's state (variables, cwd)
        if not tokens and env:                      # a plain assignment `T=/tmp/x`
            for k, v in env.items():
                assigns[k] = _resolved_value(v, assigns) if certain else None
        elif b in ("export", "declare", "typeset", "local", "readonly"):
            for a in tokens[1:]:
                m = ASSIGN_TOKEN_RE.match(a)
                if m:
                    assigns[m.group(1)] = _resolved_value(m.group(2), assigns) if certain else None
        elif b in ("read", "unset", "for", "select", "getopts", "mapfile", "readarray", "printf"):
            for a in tokens[1:]:
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", a):
                    assigns[a] = None
        if flags["shell_state"]:
            cur = None
            assigns = {k: None for k in assigns}
        elif b in ("cd", "pushd"):
            cur = _resolve_cd(tokens, cur, assigns) if (certain and b == "cd" and not funcs) else None
        elif b == "popd":
            cur = None
        if head in ("fi", "done", "esac") and compound:
            compound -= 1


def _git_parse(tokens: list, cwd, assigns: dict):
    """Read `git [global opts] <sub> <args>`. returns (gitcwd, sub, subargs).

    Repeated -C options are joined (git -C a -C b == a/b). With --git-dir / --work-tree,
    which repo is affected can't be decided statically, so gitcwd=None."""
    args, i, gcwd = tokens[1:], 0, cwd
    while i < len(args):
        a = args[i]
        if a == "-C":
            v = _resolved_value(args[i + 1], assigns) if i + 1 < len(args) else None
            if v is None or gcwd is None and not os.path.isabs(v):
                gcwd = None
            elif v:
                gcwd = os.path.normpath(os.path.join(gcwd or "/", v))
            i += 2
            continue
        if a in ("--git-dir", "--work-tree"):
            gcwd = None; i += 2
            continue
        if a.startswith(("--git-dir=", "--work-tree=")):
            gcwd = None; i += 1
            continue
        if a in ("-c", "--namespace", "--exec-path", "--config-env", "--super-prefix"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        break
    sub = args[i] if i < len(args) else None
    return gcwd, sub, args[i + 1:]


def _classify_target(raw: str, assigns: dict = None) -> str:
    """returns: 'catastrophic' | 'safe' | 'other'"""
    t = raw.strip().strip('"').strip("'")
    if not t:
        return "safe"
    if t.startswith(SAFE_VAR_PREFIXES):
        return "safe"
    if "$" in t or "`" in t:
        t = _resolve(t, assigns or {})
    if "$" in t or "`" in t:
        return "other"  # unresolved variables/command substitutions can't be judged statically
    expanded = os.path.expanduser(t) if t.startswith("~") else t
    norm = os.path.normpath(expanded)
    stripped_glob = norm[:-2] if norm.endswith("/*") else norm
    # catastrophic: root, home, system dirs, bare globs, the whole current directory
    if t in {"*", ".", "./", "..", "../", ".*"}:
        return "catastrophic"
    if stripped_glob in {"/", HOME} or stripped_glob in SYSTEM_DIRS:
        return "catastrophic"
    if norm == "/*":
        return "catastrophic"
    # safe: relative paths (without ..)
    if not norm.startswith("/") and ".." not in norm.split(os.sep):
        return "safe"
    # safe: under temp areas or worktree locations
    if norm.startswith(SAFE_PREFIXES) or (norm + "/").startswith(SAFE_PREFIXES):
        return "safe"
    # safe: root of a merged, clean linked worktree (wherever it lives; an unmerged one is
    # stopped earlier by worktree-guard. Avoids a prompt on every cleanup)
    if _is_linked_worktree_root(norm) and _worktree_state(norm) == "merged_clean":
        return "safe"
    return "other"


_RECURSIVE_FLAG_RE = re.compile(r"^-[a-zA-Z]*[rR]")
_FIND_ACTIONS = ("-exec", "-execdir", "-ok", "-okdir")


def _find_action_cmds(tokens: list) -> list:
    """List of commands (token lists) run by find's `-exec`/`-execdir`/`-ok`/`-okdir`."""
    out, i = [], 1
    while i < len(tokens):
        if tokens[i] in _FIND_ACTIONS:
            j = i + 1
            while j < len(tokens) and tokens[j] not in (";", "+"):
                j += 1
            if j > i + 1:
                out.append(tokens[i + 1:j])
            i = j
        i += 1
    return out


def _is_recursive_rm(tokens: list) -> bool:
    return any(_RECURSIVE_FLAG_RE.match(f) or f == "--recursive"
               for f in tokens[1:] if f.startswith("-") and f != "--")


def _find_delete_starts(tokens: list):
    """The start paths for `find <start>... -delete` / `-exec rm ...`; None for a find that doesn't delete.

    find walks the start paths recursively, so with a delete action it counts as a recursive delete of the start paths."""
    if not tokens or os.path.basename(tokens[0]) != "find":
        return None
    deleting = "-delete" in tokens
    for i, a in enumerate(tokens):
        if a in _FIND_ACTIONS:
            action = []
            for b in tokens[i + 1:]:
                if b in (";", "+"):
                    break
                action.append(b)
            if re.search(r"(^|[\s/;&|(`])(rm|unlink|trash)(\s|$)", " ".join(action)):
                deleting = True
    if not deleting:
        return None
    starts, i = [], 1
    while i < len(tokens) and tokens[i] in ("-H", "-L", "-P", "-E", "-X", "-d", "-s", "-x"):
        i += 1
    while i < len(tokens) and not tokens[i].startswith(("-", "(", "!", ")")):
        starts.append(tokens[i]); i += 1
    # Without a start path GNU find walks from the current directory (.) (`find -delete` used to slip through)
    return starts or ["."]


# find elements that don't filter (global options, actions, operators). For value-taking ones, the number of values
_FIND_NOFILTER = {"-depth": 0, "-d": 0, "-maxdepth": 1, "-mindepth": 1, "-xdev": 0, "-mount": 0,
                  "-follow": 0, "-noleaf": 0, "-ignore_readdir_race": 0,
                  "-noignore_readdir_race": 0, "-daystart": 0, "-regextype": 1, "-warn": 0,
                  "-nowarn": 0, "-true": 0, "-delete": 0, "-print": 0, "-print0": 0, "-ls": 0,
                  "(": 0, ")": 0, "!": 0, ",": 0, "-a": 0, "-o": 0, "-and": 0, "-or": 0, "-not": 0}


def _find_exec_deletes(tokens: list) -> bool:
    """Whether find calls rm, unlink or trash via -exec / -execdir etc."""
    for i, a in enumerate(tokens):
        if a in _FIND_ACTIONS:
            action = []
            for b in tokens[i + 1:]:
                if b in (";", "+"):
                    break
                action.append(b)
            if re.search(r"(^|[\s/;&|(`])(rm|unlink|trash)(\s|$)", " ".join(action)):
                return True
    return False


def _find_filtered(tokens: list) -> bool:
    """Whether find has a filter such as a name or type. `find . -name '*.pyc' -delete` is ordinary cleanup,
    but an unfiltered `find . -delete` wipes the whole current directory (same as `rm -rf .`)."""
    i = 1
    while i < len(tokens) and tokens[i] in ("-H", "-L", "-P", "-E", "-X", "-d", "-s", "-x"):
        i += 1
    while i < len(tokens) and not tokens[i].startswith(("-", "(", "!", ")")):
        i += 1   # start paths
    while i < len(tokens):
        a = tokens[i]
        if a in _FIND_ACTIONS:
            while i < len(tokens) and tokens[i] not in (";", "+"):
                i += 1
            i += 1
            continue
        if a not in _FIND_NOFILTER:
            return True
        i += 1 + _FIND_NOFILTER[a]
    return False


_OPAQUE_DELETE_RE = re.compile(r"(^|[\s;&|(`/])(rm|find|trash)\s")
_OPAQUE_ABS_RE = re.compile(r"(^|\s)[\"']?(/|~|\$\{?HOME)")


def rule_rm_guard(command: str):
    # **No bypass marker** (removed 2026-09-23). Prefixing a certain env var used to let it through,
    # but that was a "self-declaration" Claude could set by itself.
    # The point of this rule is **to make a human confirm**; if Claude can pass on its own, no confirmation happens.
    # Unlike push-freshness, there is no way to measure that an rm is "safe"; it takes judgment.
    # So hand it back to the person who judges = Claude can't pass it.
    # _commands also expands wrappers such as sudo/env/xargs, `sh -c`, eval, subshells and command substitutions.
    worst = None  # None < other < catastrophic

    def note(c):
        nonlocal worst
        if c == "catastrophic":
            worst = "catastrophic"
        elif c == "other" and worst is None:
            worst = "other"

    for cmd in _commands(command):
        tokens, assigns = cmd.tokens, cmd.assigns
        if cmd.opaque and _OPAQUE_DELETE_RE.search(cmd.raw) and _OPAQUE_ABS_RE.search(cmd.raw):
            note("other")   # a delete that can't be parsed (unclosed quotes etc.) errs on the safe side
        if not tokens:
            continue
        cmd_name = os.path.basename(tokens[0])
        targets = [t for t in tokens[1:] if not t.startswith("-")]
        if cmd.xargs:
            targets.append("$__XARGS__")   # arguments come from stdin = can't be judged statically
        if cmd_name == "trash":
            # Moving to the Trash can be undone, so allow it outside the safe areas too. Stop only catastrophic targets
            if any(_classify_target(t, assigns) == "catastrophic" for t in targets):
                note("catastrophic")
            continue
        starts = _find_delete_starts(tokens)
        if starts is not None:
            filtered = _find_filtered(tokens)
            for t in starts:
                # Filtering like `find . -name x -delete` is the norm, so the current . counts as relative.
                # Unfiltered, it is catastrophic like `rm -rf .`
                note("safe" if t in (".", "./") and filtered else _classify_target(t, assigns))
            continue
        if cmd_name != "rm" or not _is_recursive_rm(tokens):
            continue
        for t in targets:
            note(_classify_target(t, assigns))
    if worst == "catastrophic":
        return deny(
            "🛑 rm-guard (global hook): catastrophic recursive delete target detected (root, home, system dir, bare *, etc.)."
            " This operation can't be allowed. If it is truly needed, get explicit user approval and retry with the target narrowed to a specific path."
        )
    if worst == "other":
        return deny(
            "⚠️ rm-guard (global hook): recursive delete outside temp areas and relative paths detected.\n"
            "**No environment variable or marker silences this gate. This target can't be deleted with rm -r.**\n"
            "Do one of the following:\n"
            "  (1) If the target can be under /tmp, $TMPDIR, a configured worktree location, or a relative path, rewrite it that way\n"
            "  (2) If it uses a variable, assign it in the same command or expand it to a literal path\n"
            "  (3) On macOS, move it to the Trash with `trash <path>` (allowed because it can be undone; only when the user has approved the delete)\n"
            "  (4) Where trash isn't available (Linux, etc.), **explain to the user what will be deleted and why, and have the user run it**\n"
            "(Check: is the target exactly the intended path? / does it sweep up uncommitted work or "
            "another session's worktree?)"
            " (Get user approval first if it touches user assets.)"
            " Wrapping it in sudo, xargs, sh -c, eval, find -delete, etc. gets the same verdict."
        )
    return None


# ------------------------------------------------------------ push-freshness
PUSH_RE = re.compile(r"\bgit\s+push\b")


def _effective_cwd(command: str):
    """The working directory the git rules should look at. Rather than the tool's cwd, follow
    `cd <path> && …` and `git -C <path> …` in the command and return where git actually runs.
    (Incident: `cd ~/.claude/skills && git commit` was judged in another repo's cwd and wrongly denied, 2026-09-21)
    Falls back to the tool's cwd if undecidable."""
    cwd = _CWD if (_CWD and os.path.isdir(_CWD)) else None
    if not command:
        return cwd
    m = re.search(r"\bgit\s+-C\s+(\S+)", command)
    if m:
        cand = os.path.expanduser(m.group(1).strip("'\""))
        cand = cand if os.path.isabs(cand) else os.path.join(cwd or os.getcwd(), cand)
        return cand if os.path.isdir(cand) else cwd
    cur = cwd
    for seg in re.split(r"&&|;|\|\||\n", command):
        m = re.match(r"\s*cd\s+(\S+)", seg)
        if m:
            cand = os.path.expanduser(m.group(1).strip("'\""))
            cand = cand if os.path.isabs(cand) else os.path.join(cur or os.getcwd(), cand)
            if os.path.isdir(cand):
                cur = os.path.normpath(cand)
        if re.search(r"\bgit\s+(commit|push)\b", seg):
            return cur
    return cur

# git calls that inspect the path being deleted (worktree-guard) want "that path's repo", so they run
# without the GIT_DIR etc. the hook inherited. The push/commit freshness checks use the same
# environment as the command being run (inherited values as is)
_GIT_LOCAL_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                   "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX")
GIT_ENV = {k: v for k, v in os.environ.items() if k not in _GIT_LOCAL_VARS}


def _git(args, cwd, timeout=8, env=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env,
    )


def _remote_default(cwd, env=None):
    """The default branch origin reports right now (ls-remote, read-only). Asked first because the local
    origin/HEAD is not updated by fetch. None if unreachable or auth is needed (don't make anyone wait)."""
    try:
        r = subprocess.run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL,
                           text=True, timeout=5, env={**(env or os.environ), "GIT_TERMINAL_PROMPT": "0"})
    except (subprocess.TimeoutExpired, OSError):
        return None
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", r.stdout, re.M) if r.returncode == 0 else None
    return m.group(1) if m else None


def _default_branch(cwd, online=True, env=None):
    """The repo's default branch. Ask origin; if unreachable, the local origin/HEAD; failing that, whichever of origin/main or origin/master exists.
    online=False doesn't ask origin (so commits don't hit the network every time)."""
    name = _remote_default(cwd, env) if online else None
    if name:
        return name
    r = _git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd, timeout=5, env=env)
    name = r.stdout.strip() if r.returncode == 0 else ""
    if name.startswith("origin/"):
        return name[len("origin/"):]
    for cand in ("main", "master"):
        if _git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{cand}"], cwd, timeout=5, env=env).returncode == 0:
            return cand
    return None


def rule_push_freshness(command: str):
    # **No bypass marker.** Prefixing a certain env var to the command used to let it through
    # without checking anything, but that was a "self-declaration" Claude could make just by
    # adding a string (the gate could be passed with zero checks).
    # What this rule wants is not a claim of "merged the latest" but its **result**, and the
    # result is measured mechanically below as the behind count. Don't replace a measurement with a claim.
    if not PUSH_RE.search(command):
        return None
    cwd = _effective_cwd(command)
    if cwd is None:
        return None
    try:
        # is it a git repo / current branch
        r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        if r.returncode != 0:
            return None
        branch = r.stdout.strip()
        base = _default_branch(cwd)
        if base is None or branch in (base, "main", "master", "HEAD"):
            return None  # pushing the default branch itself is out of scope
        # fetch origin/<default branch> (network; offline/slow passes through = push needs the network anyway)
        _git(["fetch", "--quiet", "origin", "--", base], cwd)
        r = _git(["rev-list", "--count", f"HEAD..origin/{base}"], cwd)
        if r.returncode != 0:
            return None
        behind = int(r.stdout.strip() or "0")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None  # if undecidable, stay out of the way
    if behind == 0:
        return None
    return deny(
        f"🛑 push-freshness gate (global hook): the current branch '{branch}' is "
        f"{behind} commits behind origin/{base}.\n"
        f"Pushing a branch still cut from an old {base} misses not only text conflicts but "
        "semantic drift (changed function signatures, etc.: the auto-merge succeeds but it breaks at run time). "
        "Before pushing, bring in the latest and confirm with tests that both sides work together:\n"
        f"  (1) git merge origin/{base}   (resolve any conflicts)\n"
        "  (2) run the project's full test suite/build and confirm it passes\n"
        "  (3) run the push again as is\n"
        f"(If you work with rebase, git rebase origin/{base} instead of merge is fine.)\n"
        "**No environment variable or marker silences this gate.** It passes automatically once behind is 0.\n"
        "If you really need to push on an old base (a backport, etc.), the user should run it directly, "
        "not Claude."
    )


# ----------------------------------------------------- main-commit-freshness
COMMIT_RE = re.compile(r"\bgit\s+commit\b")


def rule_main_commit_freshness(command: str):
    """Stop commits on top of a stale main.

    rule_push_freshness is for feature branches only (main is explicitly excluded), so nobody
    was watching for "local main itself is stale". Merges happen on the remote, so local main
    doesn't follow automatically; forget to pull and you commit on a stale main → the push is
    rejected as non-fast-forward and you have to redo it with a rebase.

    A deny is right here, not PostToolUse additionalContext: stopping before the commit avoids
    rework, rather than saying "that was stale" afterwards. Catching up with a pull after a merge
    has nothing to block, so git-freshness.py (PostToolUse) handles that.
    """
    if not COMMIT_RE.search(command):
        return None
    commits = [c for c in _commands(command) if c.tokens
               and os.path.basename(c.tokens[0]) == "git"
               and _git_parse(c.tokens, c.cwd, c.assigns)[1] == "commit"]
    # The marker works only as an env var assignment at the start of the commit command itself
    # (a string in an echo or a comment doesn't pass).
    if commits and all(_marker(c, "MAIN_FRESHNESS_OK") for c in commits):
        return None
    cwd = _effective_cwd(command)
    if cwd is None:
        return None
    try:
        r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        if r.returncode != 0:
            return None
        branch = r.stdout.strip()
        if branch not in ("main", "master", _default_branch(cwd, online=False)):
            return None  # feature branches are checked by rule_push_freshness at push time
        # fetch is best-effort (offline passes through = doesn't get in the way of the commit)
        _git(["fetch", "--quiet", "origin", "--", branch], cwd)
        r = _git(["rev-list", "--count", f"HEAD..origin/{branch}"], cwd)
        if r.returncode != 0:
            return None
        behind = int(r.stdout.strip() or "0")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None  # if undecidable, stay out of the way
    if behind == 0:
        return None
    return deny(
        f"🛑 main-freshness gate (global hook): local '{branch}' is "
        f"{behind} commits behind origin/{branch}.\n"
        "Committing now gets the push rejected as non-fast-forward, and you will have to redo it."
        " Also, if a job runs this checkout directly, staying stale means "
        "**the merged code never runs**.\n"
        f"  (1) git pull --ff-only origin {branch}   (if uncommitted changes conflict, commit/stash them first; "
        "decide by hand, auto-stash causes accidents)\n"
        "  (2) if all is well, run the commit again\n"
        f"Only if you deliberately commit on an old {branch}, retry with `MAIN_FRESHNESS_OK=1 ` at the start."
    )


# ------------------------------------------------------------- worktree-guard
# Forbid deleting unmerged worktrees (the enforcement point that keeps unrecovered work from being lost.
# rm-guard treats paths under the configured worktree_dirs as SAFE, so this rule must run before rm-guard).
# Wherever they live (including Claude Code's standard <repo>/.claude/worktrees/), it checks whether the
# target is a linked worktree itself or a folder containing one, via `git worktree list` and a scan for `.git` files.
# Under worktree_dirs, undecidable paths (missing, or a variable with an unknown destination) are stopped too (2026-10-06)


def _worktree_state(path: str):
    """'merged_clean' | 'unmerged' | 'unknown'"""
    p = os.path.normpath(os.path.expanduser(path))
    if not os.path.isdir(p):
        return "unknown"
    try:
        if _git(["status", "--porcelain"], p, env=GIT_ENV).stdout.strip():
            return "unmerged"  # dirty = there is unrecovered work
        # Merged if HEAD is fully contained in any one base.
        # Don't decide by the first base that resolves — in a repo where origin/main is older than local
        # main, that misses "already merged into local main" and denies (measured: 21 commits apart).
        resolved = False
        default = _default_branch(p, env=GIT_ENV)
        bases = ([f"origin/{default}", default] if default not in (None, "main", "master") else []) \
            + ["origin/main", "main", "origin/master", "master"]
        for base in bases:
            r = _git(["rev-list", "--count", "HEAD", "^" + base], p, env=GIT_ENV)
            if r.returncode == 0:
                resolved = True
                if int(r.stdout.strip() or "0") == 0:
                    return "merged_clean"
        # A squash merge creates one commit with a different SHA on main, so by topology it looks unmerged forever.
        # If the head of this branch's MERGED PR matches the current HEAD, the work is in main
        # (same check as spinoff-session's reap.sh. No gh, a failure or a mismatch falls back to the above)
        if _squash_merged(p):
            return "merged_clean"
        return "unmerged" if resolved else "unknown"
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return "unknown"


def _squash_merged(p: str) -> bool:
    branch = _git(["symbolic-ref", "--short", "-q", "HEAD"], p, env=GIT_ENV).stdout.strip()
    head = _git(["rev-parse", "HEAD"], p, env=GIT_ENV).stdout.strip()
    if not branch or not head:
        return False
    try:
        r = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "merged",
             "--json", "headRefOid", "--jq", ".[].headRefOid"],
            cwd=p, capture_output=True, text=True, timeout=8, env=GIT_ENV,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0 and head in r.stdout.split()


def _marker(cmd, name: str) -> bool:
    """Whether the bypass marker (`NAME=1 <cmd>`) is an env var assignment at the start of that command itself.
    It used to pass if it appeared anywhere in the command string, so an echo or a comment let it through."""
    return cmd.env.get(name) == "1"


def _under_worktrees(p: str) -> bool:
    """Whether p is one of the configured worktree_dirs or under one."""
    return any(p == d or p.startswith(d + "/") for d in WORKTREE_DIRS)


def _is_linked_worktree_root(p: str) -> bool:
    """Whether p is the root of a linked worktree (its `.git` is a file pointing to gitdir: …/worktrees/…)."""
    try:
        with open(os.path.join(p, ".git"), errors="replace") as f:
            return "/worktrees/" in f.read(4096).replace("\\", "/")
    except OSError:
        return False


def _linked_worktrees_under(p: str, follow: str = "") -> list:
    """Real paths of linked worktrees that are p itself or below p (excluding the main working tree).
    Combines `git worktree list` of the repo p belongs to with a scan for `.git` files inside p.
    If the scan hits its limit, a None is mixed in (undecidable = block).
    [] if p doesn't exist or can't be read (left to rm-guard).
    follow is find's symlink handling ("H" follows start paths only, "L" follows inside too).
    rm deletes only the link itself, so without follow the link target is not inspected."""
    if not os.path.isdir(p) or (os.path.islink(p) and not follow):
        return []
    if follow:
        p = os.path.realpath(p)
    try:
        r = _git(["worktree", "list", "--porcelain"], p, env=GIT_ENV)
    except (subprocess.TimeoutExpired, OSError):
        r = subprocess.CompletedProcess([], 1, "", "")
    found = []
    if r.returncode == 0:
        paths = [line[len("worktree "):] for line in r.stdout.splitlines() if line.startswith("worktree ")]
        rp = os.path.realpath(p)
        found = [w for w in (os.path.realpath(x) for x in paths[1:])
                 if w == rp or w.startswith(rp.rstrip("/") + "/")]
    # Also catch worktrees of another repo inside p (a parent folder not under git, or inside an unrelated repo)
    scanned, complete = _scan_worktree_roots(p, follow_links=follow == "L")
    return list(dict.fromkeys(found + scanned + ([] if complete else [None])))


# Not places where worktrees live, so don't descend (they are large and would use up the scan budget fast)
_SCAN_SKIP = {".git", "node_modules"}


# Remaining number of folders to look at in one hook call (not reset per glob match or per target)
_scan_budget = None


def _scan_worktree_roots(p: str, follow_links: bool = False):
    """Roots of linked worktrees under p (folders whose `.git` is a file pointing to gitdir: …/worktrees/…),
    and whether the scan finished. A submodule's `.git` file points to modules/, so it doesn't count.
    No depth limit; instead at most 20000 folders per command in total (so deleting a huge folder
    or a glob with many matches doesn't keep anyone waiting).
    If cut off at the limit, complete=False (can't claim there is no worktree where we didn't look).
    follow_links is for `find -L` and also follows links to folders (each real path is visited once)."""
    global _scan_budget
    if _scan_budget is None:
        _scan_budget = int(os.environ.get("GUARDS_SCAN_LIMIT") or 20000)   # the env var is for tests
    if os.path.basename(p.rstrip("/")) in _SCAN_SKIP:
        return [], True
    found, stack, visited = [], [p], set()
    while stack:
        d = stack.pop()
        _scan_budget -= 1
        if _scan_budget < 0:
            return found, False
        if follow_links:
            rd = os.path.realpath(d)
            if rd in visited:
                continue
            visited.add(rd)
        try:
            entries = list(os.scandir(d))
        except FileNotFoundError:
            continue
        except OSError:
            # can't check inside an unreadable folder (sudo rm could still delete it)
            return found, False
        for e in entries:
            if e.name == ".git":
                if e.is_file(follow_symlinks=False):
                    try:
                        with open(e.path, errors="replace") as f:
                            head = f.read(4096)
                    except OSError:
                        head = ""
                    if "/worktrees/" in head.replace("\\", "/"):
                        found.append(os.path.realpath(d))
                continue
            if e.name not in _SCAN_SKIP and e.is_dir(follow_symlinks=follow_links):
                stack.append(e.path)
    return found, True


def _split_top_commas(body: str) -> list:
    parts, depth, cur = [], 0, ""
    for c in body:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += c
    return parts + [cur]


_SEQ_RE = re.compile(r"^(-?\d+|[A-Za-z])\.\.(-?\d+|[A-Za-z])(?:\.\.(-?\d+))?$")


def _brace_seq(body: str, limit: int = 256):
    """List the contents of `{1..3}`, `{a..c}`, `{01..10..2}` (up to limit + 1 items, so `{1..1000000000}`
    doesn't hang). None if not a range."""
    m = _SEQ_RE.match(body)
    if not m:
        return None
    a, b, step = m.group(1), m.group(2), abs(int(m.group(3) or 1)) or 1
    if a.lstrip("-").isdigit() and b.lstrip("-").isdigit():
        x, y = int(a), int(b)
        width = max(len(a), len(b)) if (a.lstrip("-").startswith("0") or b.lstrip("-").startswith("0")) else 0
        rng = range(x, y + 1, step) if x <= y else range(x, y - 1, -step)
        return [str(n).zfill(width) if width else str(n) for n in itertools.islice(rng, limit + 1)]
    if a.isalpha() and b.isalpha():
        x, y = ord(a), ord(b)
        rng = range(x, y + 1, step) if x <= y else range(x, y - 1, -step)
        return [chr(n) for n in itertools.islice(rng, limit + 1)]
    return None


def _brace_expand(s: str, limit: int = 256) -> list:
    """bash brace expansion (`a{b,c}d` → abd acd, nesting allowed, ranges like `{1..3}` too).
    If the expansion exceeds limit, stop at limit + 1 items (the caller treats it as "can't fully check")."""
    depth, start = 0, None
    for i, c in enumerate(s):
        if c == "{" and not (i and s[i - 1] == "$"):
            if depth == 0:
                start = i
            depth += 1
        elif c == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                body = s[start + 1:i]
                parts = _split_top_commas(body)
                if len(parts) == 1:
                    parts = _brace_seq(body, limit) or parts
                if len(parts) > 1:
                    out = []
                    for part in parts:
                        out.extend(_brace_expand(s[:start] + part + s[i + 1:], limit))
                        if len(out) > limit:
                            break
                    return out[:limit + 1]
                start = None
    return [s]


# extglob (`@(a|b)`, `!(x)`, etc.). The contents are not interpreted; that level is treated as `*`
_EXTGLOB_RE = re.compile(r"[?*+@!]\(")


def _has_glob(s: str) -> bool:
    return glob.has_magic(s) or bool(_EXTGLOB_RE.search(s))


def _glob_superset(b: str, limit: int = 256) -> list:
    """Collect the paths glob b could match in a shell, erring on the side of too many.
    Shell options (dotglob, nocaseglob, extglob, globstar) change what matches, so include names
    starting with `.`, ignore case, and let extglob levels match anything.
    `**` descends any number of levels, so take the whole folder before it (the worktree scan covers what's below).
    If matches exceed limit, stop at limit + 1 (the caller treats it as can't fully check)."""
    absolute = b.startswith("/")
    cur = ["/" if absolute else "."]
    for c in (c for c in b.split("/") if c):
        if "**" in c:
            return cur
        if not _has_glob(c):
            cur = [q for q in (os.path.join(d, c) for d in cur) if os.path.lexists(q)]
            continue
        pat = "*" if _EXTGLOB_RE.search(c) else c.lower()
        nxt = []
        for d in cur:
            try:
                names = os.listdir(d)
            except OSError:
                continue
            nxt += [os.path.join(d, n) for n in names if fnmatch.fnmatchcase(n.lower(), pat)]
            if len(nxt) > limit:
                return nxt[:limit + 1]
        cur = nxt
    return cur


def _worktrees_in_target(p: str, limit: int = 256, follow: str = "") -> list:
    """Linked worktrees that deleting p could remove (None marks "couldn't fully check").
    Brace expansion works as in the shell; globs (`*` etc.) are expanded broadly to whatever could match. A quoted `[`
    etc. reaches the shell literally, but arrives here with the quotes stripped, so the literal path is checked too."""
    expanded = _brace_expand(p, limit)
    found = [None] if len(expanded) > limit else []
    # a quoted `{a,b}` is also passed literally by the shell
    paths = [p] if expanded != [p] and os.path.lexists(p) else []
    for b in expanded[:limit]:
        if not _has_glob(b):
            paths.append(b)
            continue
        paths.extend(_glob_superset(b, limit))
        if os.path.lexists(b):
            paths.append(b)
    paths = list(dict.fromkeys(os.path.normpath(q) for q in paths))
    if len(paths) > limit:   # a glob with too many matches counts as can't fully check, without asking git about each
        found.append(None)
        paths = paths[:limit]
    found += [w for q in paths for w in _linked_worktrees_under(q, follow)]
    return list(dict.fromkeys(found))


def _find_follow(tokens: list) -> str:
    """Whether find follows symlinks. "L" (-L, -follow) follows inside too, "H" start paths only, "" doesn't follow."""
    mode, i = "", 1
    while i < len(tokens) and tokens[i] in ("-H", "-L", "-P", "-E", "-X", "-d", "-s", "-x"):
        mode = {"-H": "H", "-L": "L", "-P": ""}.get(tokens[i], mode)
        i += 1
    return "L" if "-follow" in tokens[i:] else mode


_TMPDIR_RE = re.compile(r"^\$(?:TMPDIR\b|\{TMPDIR\}|\{TMPDIR:?-([^}$`]*)\})(.*)$", re.S)


def _tmpdir_value(s: str):
    """Resolve `$TMPDIR/x`, `${TMPDIR}/x`, `${TMPDIR:-/tmp}/x` with the TMPDIR the hook inherited.
    None if it can't be resolved."""
    m = _TMPDIR_RE.match(s)
    if not m or "$" in m.group(2) or "`" in m.group(2):
        return None
    base = os.environ.get("TMPDIR") or m.group(1)
    return os.path.normpath(base + m.group(2)) if base else None


def _inside_worktree(p: str) -> bool:
    """Whether p is a subpath inside a worktree (neither the worktree root itself nor a folder containing the root)."""
    d = p
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    if not d:
        return False
    try:
        r = _git(["rev-parse", "--show-toplevel"], d, env=GIT_ENV)
    except (subprocess.TimeoutExpired, OSError):
        return False
    if r.returncode != 0 or not r.stdout.strip():
        return False
    # git returns real paths (macOS /var → /private/var, etc.), so compare both sides as real paths
    top, rp = os.path.realpath(r.stdout.strip()), os.path.realpath(p)
    return any(top.startswith(os.path.realpath(d) + "/") for d in WORKTREE_DIRS) and rp.startswith(top + "/")


def rule_worktree_guard(command: str):
    cwd0 = os.path.normpath(_CWD) if _CWD else ""
    cwd_in_wt = bool(cwd0) and _under_worktrees(cwd0)
    if not cwd_in_wt and not any(w in command for w in ("worktree", "rm", "trash", "find")):
        return None  # fast pass-through
    # When a relative path's or variable's destination is unknown: could the context involve a worktree?
    risky_unknown = any(os.path.basename(d) in command for d in WORKTREE_DIRS) or cwd0 in WORKTREE_DIRS
    targets = []   # (display name, absolute path or None = undecidable)
    for cmd in _commands(command):
        tokens = cmd.tokens
        if not tokens or _marker(cmd, "WORKTREE_RM_OK"):
            continue
        base = os.path.basename(tokens[0])
        if base == "git":
            gcwd, sub, subargs = _git_parse(tokens, cmd.cwd, cmd.assigns)
            if sub == "worktree" and subargs[:1] == ["remove"]:
                for t in (a for a in subargs[1:] if not a.startswith("-")):
                    v = _resolved_value(t, cmd.assigns)
                    if v is not None and not os.path.isabs(v):
                        v = os.path.join(gcwd, v) if gcwd else None
                    targets.append((t, os.path.normpath(v) if v else None))
            continue
        starts = _find_delete_starts(tokens)
        # A filtered `find … -delete` (`-name '*.pyc'` etc.) doesn't wipe the start path.
        # -delete can't remove non-empty folders, so outside worktree_dirs it can't remove a worktree root
        filtered = starts is not None and _find_filtered(tokens)
        filtered_delete_only = filtered and not _find_exec_deletes(tokens)
        follow = _find_follow(tokens) if starts is not None else ""
        # This rule guards against deleting a whole worktree. Deleting files inside a worktree with a filter
        # (`find . -type f -delete` etc.) is out of scope like deleting a subpath (the main working tree has the same risk)
        if starts is not None:
            paths = starts
        elif base == "trash" or (base == "rm" and _is_recursive_rm(tokens)):
            paths = [t for t in tokens[1:] if not t.startswith("-")]
        else:
            continue
        if cmd.xargs and (risky_unknown or cwd_in_wt):
            targets.append(("(xargs input)", None))
        for t in paths:
            raw = t.strip('"').strip("'")
            v = _resolved_value(raw, cmd.assigns)
            if v is None and raw.startswith(SAFE_VAR_PREFIXES):
                # rm-guard treats paths under $TMPDIR as safe, so check the destination here (block if unknown)
                v = _tmpdir_value(_resolve(raw, cmd.assigns))
                if v is None:
                    targets.append((t, None))
                    continue
            if v is None:
                if risky_unknown:
                    targets.append((t, None))
                continue
            if os.path.isabs(v):
                exp = os.path.normpath(v)
                if _under_worktrees(exp):
                    targets.append((t, exp))
                elif not filtered_delete_only:
                    targets.extend((t, w) for w in _worktrees_in_target(exp, follow=follow))
                continue
            # Relative path: resolve against the cwd it runs in (`cd <worktree_dirs> && rm -rf name` etc.).
            # Subpaths inside a worktree (cleaning build/ etc.) are out of scope
            if cmd.cwd is None:
                if risky_unknown:
                    targets.append((t, None))
                continue
            exp = os.path.normpath(os.path.join(cmd.cwd, v))
            if _under_worktrees(exp):
                if not _inside_worktree(exp):
                    targets.append((t, exp))
            elif not filtered_delete_only:
                targets.extend((t, w) for w in _worktrees_in_target(exp, follow=follow))
    bad = list(dict.fromkeys(t for t, p in targets if p is None or _worktree_state(p) != "merged_clean"))
    if not bad:
        return None
    return deny(
        f"🛑 worktree-guard: trying to delete a worktree that is unmerged or can't be judged: {', '.join(bad[:3])}\n"
        "Deleting unmerged worktrees is forbidden (unrecovered work would be lost). If it is merged into the default branch and clean, it passes automatically."
        " A folder too large to confirm it holds no worktree is also blocked as undecidable."
        " If it really must go, get the user's explicit OK and retry with `WORKTREE_RM_OK=1 ` at the start of the delete command itself"
        " (e.g. `WORKTREE_RM_OK=1 git worktree remove <path>`)."
    )


# ---------------------------------------------------------- gh-comments-guard
def rule_gh_comments_guard(command: str):
    if "--comments" not in command:
        return None  # fast pass-through
    for seg in _split_segments(command):
        try:
            tokens = shlex.split(seg)
        except ValueError:
            continue
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens.pop(0)
        if not tokens or os.path.basename(tokens[0]) != "gh":
            continue
        sub = [t for t in tokens[1:] if not t.startswith("-")]
        if len(sub) >= 2 and sub[0] == "issue" and sub[1] == "view" and "--comments" in tokens \
                and not any(t == "--json" or t.startswith("--json=") for t in tokens):
            return deny(
                "🛑 gh-comments-guard: on an issue with zero comments, `gh issue view --comments` prints nothing,"
                " body included, and exits 0 (measured with gh 2.96.0). Use the `--json title,body,comments` form."
            )
    return None


# ------------------------------------------------------------ pip-freeze-guard
def rule_pip_freeze_guard(command: str):
    if "freeze" not in command:
        return None  # fast pass-through
    for cmd in _commands(command):
        tokens = cmd.tokens
        if _marker(cmd, "PIP_FREEZE_OK"):
            continue
        if len(tokens) >= 2 and os.path.basename(tokens[0]) in ("pip", "pip3") and tokens[1] == "freeze":
            return deny(
                "🛑 pip-freeze-guard: venvs created by uv have no pip, so `pip freeze` silently returns nothing"
                " (the empty-backup-file accident). Use `uv pip freeze`. If you mean it in a plain pip environment,"
                " prefix `PIP_FREEZE_OK=1 `."
            )
    return None


RULES = [
    rule_worktree_guard,      # before rm-guard (SAFE_PREFIXES lets paths under worktree_dirs through)
    rule_rm_guard,
    rule_push_freshness,
    rule_main_commit_freshness,
    rule_gh_comments_guard,
    rule_pip_freeze_guard,
]


_PERMISSION_MODE = ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    global _CWD, _PERMISSION_MODE
    _CWD = data.get("cwd") or os.getcwd()
    _PERMISSION_MODE = data.get("permission_mode") or ""
    command = (data.get("tool_input") or {}).get("command", "")
    # deny beats ask. Even after a rule returns ask, evaluate the remaining rules and return deny
    # if any denies (don't let an ask-worthy operation chained with a dangerous one through as ask).
    pending_ask = None
    for rule in RULES:
        try:
            result = rule(command)
        except Exception as e:  # noqa: BLE001
            # an abnormal hook exit counts as "allow", so on our own bug err on the safe side (ask)
            msg = (f"⚠️ bash-guard: exception while evaluating rule {rule.__name__} "
                   f"({type(e).__name__}: {e}). Erring on the safe side (ask or deny).")
            result = deny(msg) if _PERMISSION_MODE == "bypassPermissions" else ask(msg)
        if not result:
            continue
        decision = result.get("hookSpecificOutput", {}).get("permissionDecision")
        if decision == "ask":
            pending_ask = pending_ask or result
            continue
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    if pending_ask:
        print(json.dumps(pending_ask, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
