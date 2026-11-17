"""Shell-command parsing shared by this plugin's hooks (dev_flow_gate.py, commit_gate.py).

commands() finds the calls to given executables in a Bash command, looking through heredocs, wrappers
(env, command, timeout, ...), `cd`, `export` and `sh -c '...'`. It never runs anything.
"""
import os
import re
import shlex

# Heredoc: the rest of the <<[-]['"]DELIM['"] line (group 4), the body (group 5), the closing DELIM line
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)(\w+)\2([^\n]*)\n(.*?)\n[ \t]*\3[ \t]*(?=\n|$)", re.S)
HEREDOC_MARK_RE = re.compile(r"<<__HEREDOC_(\d+)__")
ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
# Wrappers that can precede a command, and their options that take a value (skipped so we can see the command inside)
_WRAPPERS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "command": set(), "builtin": set(), "exec": {"-a"}, "nohup": set(), "time": set(),
    "nice": {"-n", "--adjustment"}, "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "-D", "--chdir"},
    "stdbuf": {"-i", "-o", "-e"},
}
_KEYWORDS = {"!", "{", "}", "if", "then", "else", "elif", "do", "while", "until", "time"}


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
                return env, []  # command -v X only looks X up, it does not run it
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


def strip_comments(command):
    """Drop `# ...` to the end of the line where `#` starts a word outside quotes, as the shell does.
    A `#` inside a word (`docs/a#b.md`) or inside quotes stays (shlex would cut the word and the rest of the line)."""
    out, i, quote, n = [], 0, None, len(command)
    subst, boundary = 0, True  # open $( ... ) count; whether the next character starts a word
    while i < n:
        ch = command[i]
        was, boundary = boundary, False
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                out.append(command[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch == "\\" and i + 1 < n:
            out.append(ch + command[i + 1])
            i += 1
        elif ch in "'\"":
            quote = ch
            out.append(ch)
        elif ch == "#" and was:
            while i < n and command[i] != "\n":
                i += 1
            boundary = True
            continue
        elif ch == "$" and command[i + 1:i + 2] == "(":
            subst += 1
            out.append("$(")
            i += 1
        elif ch == "(" and subst:
            subst += 1  # a subshell inside $( ... ): its ) is not the one that ends the substitution
            out.append(ch)
            boundary = True
        elif ch == ")" and subst:
            subst -= 1  # closes a $( ... ): the word goes on, so a # right after it is not a comment
            out.append(ch)
        else:
            out.append(ch)
            boundary = ch in " \t\n;&|()"
        i += 1
    return "".join(out)


def lex(command):
    """(tokens, heredoc bodies), or None when shlex cannot read the command (an unbalanced quote, say)."""
    command, docs = split_heredocs(command)
    command = command.replace("\\\n", " ")  # a trailing \ continues the line
    try:
        # A newline also separates commands (newlines inside quotes are kept)
        lx = shlex.shlex(strip_comments(command), posix=True, punctuation_chars=";&|()\n")
        lx.commenters = ""  # comments were removed above, only where they start a word
        lx.whitespace = " \t\r"
        lx.whitespace_split = True
        return list(lx), docs
    except ValueError:
        return None


def commands(command, exes, cwd=None, _depth=0):
    """Return the calls to the executables in `exes` (basenames) in a Bash command as
    [{"exe", "args", "env", "stdin", "docs", "cwd"}].

    Heredoc bodies are pulled out before lexing (so a ' or # in the body cannot break it). stdin is the index of the
    heredoc passed to that call with `<<`. cwd is the directory that it runs in (follows earlier `cd`s; None if unknown).
    Also looks through wrappers such as env, command and timeout, and inside `sh -c '...'`.
    A command that shlex cannot read yields nothing (lean towards not stopping, so symbols a PR body may contain don't misfire)."""
    lexed = lex(command)
    if lexed is None:
        return []
    toks, docs = lexed
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
                for call in commands(rest[k + 1], exes, cwd, _depth + 1):
                    call["env"] = {**env, **call["env"]}
                    out.append(call)
            continue
        if exe not in exes:
            continue
        stdin, args = None, []
        for a in rest[1:]:
            m = HEREDOC_MARK_RE.fullmatch(a)
            if m:
                stdin = int(m.group(1))
            else:
                args.append(a)
        out.append({"exe": exe, "args": args, "env": env, "stdin": stdin, "docs": docs, "cwd": cwd})
    return out
