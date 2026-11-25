#!/usr/bin/env python3
"""Stop hook: catch file links in Claude's last reply that the desktop app's file pane cannot open.

The Claude desktop app opens a linked file only when it is inside the session's folders: the working
directory, the directories added to the session, and the session scratchpad. A link to a file that exists
only on another branch, sits outside those folders, or is relative to the wrong folder does nothing when
clicked. This hook finds such links and blocks Stop once, so Claude fixes the reply.

What counts:
  - Markdown links `[label](target)` (and `![alt](target)`) outside code blocks and inline code.
  - Skipped: URLs (`scheme://...`, `mailto:` and other `scheme:` targets), in-app anchors (`#...`),
    targets with no letter or digit (a placeholder such as `…`).
  - A `#fragment`, a `:line` or `:line:col` suffix is dropped and %-escapes (`%28`, `%20`) are decoded.
  - Paths in backticks are not checked: in replies they are mostly commands, system paths and paths on
    other machines.

Openable = the target exists and resolves (symlinks followed) inside one of the session folders. The
added directories are not in the Stop input; they are read from the newest `environment` entry in the
transcript (`additionalWorkingDirectories`, `scratchpadDirectory`). When that entry or the scratchpad is
not available, an existing target outside the working directory passes (it may be in a folder we cannot
see); a missing one still fires.

Runs only in the desktop app (CLAUDE_CODE_ENTRYPOINT=claude-desktop); a terminal has no file pane.
Mode (userConfig `link_check`): enforce (default) blocks Stop once per turn, observe only records the
fire under ${CLAUDE_PLUGIN_DATA}/link-check/ (one file per day, kept 30 days), off does nothing.
Never calls a model or the network. Any internal error exits 0 silently.
"""
import json
import os
import re
import sys
import time
from urllib.parse import unquote

KEEP_DAYS = 30
MAX_LISTED = 8
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", re.M | re.S)
INLINE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"!?\[[^\]\n]*\]\((<[^>\n]+>|[^)\s]+)(?:\s+\"[^\"\n]*\")?\)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
LINE_SUFFIX = re.compile(r":\d+(?::\d+)?$")


def mode() -> str:
    m = (os.environ.get("CLAUDE_PLUGIN_OPTION_LINK_CHECK") or "enforce").strip().lower()
    return m if m in ("enforce", "observe", "off") else "enforce"


def link_targets(text: str) -> list:
    """Path targets of the Markdown links in text, normalized, in order, without duplicates."""
    body = INLINE.sub("", FENCE.sub("", text))
    out = []
    for m in LINK.finditer(body):
        t = m.group(1)
        if t.startswith("<") and t.endswith(">"):
            t = t[1:-1]
        if t.startswith("#") or "://" in t:
            continue
        # "README.md:42" looks like a scheme to the regex; it is a path when what follows is a line number
        if SCHEME.match(t) and not LINE_SUFFIX.search(t):
            continue
        t = unquote(LINE_SUFFIX.sub("", t.split("#", 1)[0]))
        if not re.search(r"[A-Za-z0-9_]", t) or t in out:
            continue
        out.append(t)
    return out


def session_env(transcript_path: str) -> dict:
    """The newest environment snapshot in the transcript, or {}."""
    snap = {}
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"environment"' not in line or '"attachment"' not in line:
                    continue
                try:
                    a = json.loads(line).get("attachment") or {}
                except ValueError:
                    continue
                if a.get("type") == "environment" and isinstance(a.get("snapshot"), dict):
                    snap = a["snapshot"]
    except (OSError, TypeError):
        return {}
    return snap


def _inside(path: str, root: str) -> bool:
    r = os.path.realpath(root)
    return path == r or path.startswith(r.rstrip("/") + "/")


def unopenable(targets: list, cwd: str, roots: list, folders_known: bool) -> list:
    """[(target, reason)] for the targets the file pane cannot open."""
    bad = []
    for t in targets:
        p = os.path.expanduser(t) if t.startswith("~/") else t
        p = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p))
        if not os.path.exists(p):
            bad.append((t, "not found" + ("" if os.path.isabs(t) or t.startswith("~/") else " from the working directory")))
        elif not any(_inside(p, r) for r in roots):
            if folders_known:
                bad.append((t, "outside the session folders"))
    return bad


def reason_text(bad: list) -> str:
    lines = [f"link-check: {len(bad)} file link(s) in your last reply can't be opened in the desktop app's file pane, "
             "which opens only files inside the working directory, the added directories and the scratchpad:"]
    lines += [f"- {t} ({why})" for t, why in bad[:MAX_LISTED]]
    if len(bad) > MAX_LISTED:
        lines.append(f"- … and {len(bad) - MAX_LISTED} more")
    lines += [
        "Fix it in a short follow-up that repeats the corrected links:",
        "- On another branch or commit: `git show <ref>:<path>` into the scratchpad and send it with SendUserFile, "
        "or link a GitHub blob URL pinned to a commit SHA.",
        "- Outside the session folders: copy it into the scratchpad, or send it with SendUserFile.",
        "- Wrong path: write it relative to the working directory, or as the full absolute path of a scratchpad file.",
    ]
    return "\n".join(lines)


def observe_dir() -> str:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    base = data if data else os.path.expanduser("~/.claude/state/guards")
    return os.path.join(base, "link-check")


def record(session_id: str, bad: list) -> None:
    d = observe_dir()
    os.makedirs(d, exist_ok=True)
    now = time.time()
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if name.endswith(".jsonl") and now - os.path.getmtime(p) > KEEP_DAYS * 86400:
            os.remove(p)
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "session_id": session_id,
           "targets": [{"target": t, "reason": why} for t, why in bad]}
    with open(os.path.join(d, time.strftime("%Y-%m-%d") + ".jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    m = mode()
    if m == "off" or os.environ.get("CLAUDE_CODE_ENTRYPOINT") != "claude-desktop":
        return
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return
    text = data.get("last_assistant_message")
    cwd = data.get("cwd")
    if not isinstance(text, str) or "](" not in text or not cwd:
        return
    targets = link_targets(text)
    if not targets:
        return
    env = session_env(data.get("transcript_path") or "")
    scratch = data.get("scratchpad_dir") or env.get("scratchpadDirectory")
    added = [d for d in env.get("additionalWorkingDirectories") or [] if isinstance(d, str)]
    roots = [cwd] + ([scratch] if scratch else []) + added
    bad = unopenable(targets, cwd, roots, folders_known=bool(env) and bool(scratch))
    if not bad:
        return
    if m == "observe":
        record(str(data.get("session_id") or ""), bad)
        return
    print(json.dumps({"decision": "block", "reason": reason_text(bad)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001  a broken check must never stop the session
        pass
    sys.exit(0)
