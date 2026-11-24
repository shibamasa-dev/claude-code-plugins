#!/usr/bin/env python3
"""decision-capture: when the last reply asks the user to make a decision in prose, block Stop once.

A question asked in prose is easy to miss, above all when the user runs several sessions at once. When the turn ends
with one, and the turn neither used AskUserQuestion nor ran the configured registration command, Stop is blocked once
so that Claude asks it with AskUserQuestion, records it with the registration command, or dismisses with a reason.

  UserPromptSubmit : clears the turn mark
  PostToolUse      : marks the turn when AskUserQuestion ran, or a Bash command starting with the registration
                     command's prefix (the template up to its first `{`) completed
  Stop             : passes on stop_hook_active, a marked turn, a turn it already blocked, a scratchpad cwd, or after
                     `decision_stop_limit` dismissals in a row in this session (for DISMISS_QUIET_HOURS). Otherwise,
                     when the judge (_decision_judge.asks_decision on last_assistant_message) says the reply asks,
                     `enforce` blocks once and `observe` only logs

userConfig (exported as CLAUDE_PLUGIN_OPTION_<KEY>): decision_capture (off / observe / enforce, default off),
decision_register_command, decision_stop_limit, decision_judge (regex / openai / typesafe / google),
decision_judge_threshold, and one sensitive key per vendor.

State: per session under state_dir("decision-capture") (see _state.py); files older than GC_DAYS are removed.
Always exits 0.

CLI (the block message prints the full command):
    decision-capture.py dismiss --session <id> --why "<reason>"
"""
import fcntl
import json
import os
import re
import shlex
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _decision_judge as judge  # noqa: E402
from _state import command_for, state_dir, warn_fallback  # noqa: E402

STATE_DIR = state_dir("decision-capture", override_env="DECISION_CAPTURE_STATE_DIR")
SELF = command_for(__file__)
GC_DAYS = 30
DISMISS_QUIET_HOURS = 12  # quiet only for that day's work: half a day later the topic and the writing have moved on
MODES = ("off", "observe", "enforce")
KEY_OPTION = {"openai": "DECISION_OPENAI_API_KEY", "typesafe": "DECISION_TYPESAFE_API_KEY",
              "google": "DECISION_GOOGLE_API_KEY"}
# A Claude Code scratchpad used as the working folder (eval runs and the like): questions there are not the user's
_SCRATCHPAD_RE = re.compile(r"^(?:/private)?/tmp/claude-[^/]+/(?:.+/)?scratchpad(?:/|$)")


def option(name, default=""):
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name}", "").strip() or default


def mode():
    m = option("DECISION_CAPTURE", "off").lower()
    return m if m in MODES else "off"


def stop_limit():
    try:
        return max(1, int(float(option("DECISION_STOP_LIMIT", "3"))))
    except ValueError:
        return 3


def register_prefix():
    """The registration command up to its first placeholder, with whitespace collapsed; None when not configured."""
    t = option("DECISION_REGISTER_COMMAND")
    head = " ".join(t.split("{", 1)[0].split())
    return head or None


def now():
    return datetime.now().isoformat(timespec="seconds")


class State:
    """flock'd read-modify-write of one session's state (parallel tool calls can arrive at once)."""

    def __init__(self, sid):
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)
        self.p = os.path.join(STATE_DIR, f"{safe}.json")
        self.lock = self.p + ".lock"

    def __enter__(self):
        self.lf = open(self.lock, "w")
        fcntl.flock(self.lf, fcntl.LOCK_EX)
        try:
            with open(self.p) as f:
                self.d = json.load(f)
        except Exception:
            self.d = {}
        self.d.setdefault("turn", {})
        return self

    def __exit__(self, *a):
        tmp = self.p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p)
        fcntl.flock(self.lf, fcntl.LOCK_UN)
        self.lf.close()


def live_streak(d):
    """Dismissals in a row, or 0 once DISMISS_QUIET_HOURS have passed since the last one (or its time is unreadable:
    one extra block is better than staying quiet for good)."""
    streak = d.get("dismiss_streak", 0)
    if not streak:
        return 0
    try:
        last = datetime.fromisoformat((d.get("dismissed") or [{}])[-1]["at"])
    except (KeyError, TypeError, ValueError):
        return 0
    return 0 if datetime.now() - last >= timedelta(hours=DISMISS_QUIET_HOURS) else streak


# ------------------------------------------------------------------ events
def on_user_prompt(inp):
    with State(inp["session_id"]) as st:
        st.d["turn"] = {}


def on_post_tool_use(inp):
    tool = inp.get("tool_name")
    if tool == "AskUserQuestion":
        mark = "asked_ui"
    elif tool == "Bash":
        prefix = register_prefix()
        cmd = " ".join(str((inp.get("tool_input") or {}).get("command", "")).split())
        if not prefix or not cmd.startswith(prefix):
            return
        mark = "registered"
    else:
        return
    with State(inp["session_id"]) as st:
        st.d["turn"][mark] = now()
        st.d["dismiss_streak"] = 0


def block_reason(inp, verdict):
    sid = inp["session_id"]
    score = f"{verdict.score:.2f}" if isinstance(verdict.score, float) else "-"
    fell = f", fell back from {verdict.error}" if verdict.fell_back else ""
    lines = [
        f"[decision-capture] The last reply seems to ask the user to make a decision in prose "
        f"(judge: {verdict.backend} {score}{fell}). A question in prose is easy to miss. Before ending the turn:",
        "  - ask it with AskUserQuestion (2 to 4 options, the recommended one first, one line each)",
    ]
    template = option("DECISION_REGISTER_COMMAND")
    if template:
        lines.append(f"  - or record it with the registration command, filling in the placeholders: {template}")
    lines += [
        "  - or, if the reply does not ask for a decision (a report, a request for facts, an offer), dismiss it:",
        f"      {SELF} dismiss --session {shlex.quote(sid)} --why \"<reason>\"",
    ]
    return "\n".join(lines)


def on_stop(inp):
    m = mode()
    if m == "off" or inp.get("stop_hook_active"):
        return
    cwd = inp.get("cwd") or ""
    if _SCRATCHPAD_RE.match(cwd):
        return
    sid = inp["session_id"]
    with State(sid) as st:
        turn = st.d["turn"]
        if turn.get("registered") or turn.get("asked_ui") or turn.get("blocked"):
            return
        if live_streak(st.d) >= stop_limit():
            return
    backend = option("DECISION_JUDGE", "regex").lower()
    try:
        threshold = float(option("DECISION_JUDGE_THRESHOLD")) if option("DECISION_JUDGE_THRESHOLD") else None
    except ValueError:
        threshold = None
    key = option(KEY_OPTION.get(backend, "_"))
    verdict = judge.asks_decision(inp.get("last_assistant_message") or "", backend, key, threshold)
    if not verdict.asks:
        return
    with State(sid) as st:
        entry = {"at": now(), "mode": m, "backend": verdict.backend, "score": verdict.score}
        if verdict.fell_back:
            entry["error"] = verdict.error
        st.d.setdefault("judged", []).append(entry)
        st.d["judged"] = st.d["judged"][-50:]
        if m == "enforce":
            st.d["turn"]["blocked"] = now()
            st.d["blocks"] = st.d.get("blocks", 0) + 1
    if m == "enforce":
        print(json.dumps({"decision": "block", "reason": block_reason(inp, verdict)}, ensure_ascii=False))


def gc():
    try:
        cutoff = time.time() - GC_DAYS * 86400
        for name in os.listdir(STATE_DIR):
            p = os.path.join(STATE_DIR, name)
            if os.path.getmtime(p) < cutoff:
                os.unlink(p)
    except OSError:
        pass


# --------------------------------------------------------------------- cli
def cli_dismiss(argv):
    sid, why, i = None, "", 0
    while i < len(argv):
        if argv[i] == "--session" and i + 1 < len(argv):
            sid, i = argv[i + 1], i + 2
        elif argv[i] == "--why" and i + 1 < len(argv):
            why, i = argv[i + 1], i + 2
        else:
            i += 1
    if not sid or not why.strip():
        print("usage: decision-capture.py dismiss --session <id> --why \"<reason>\"", file=sys.stderr)
        return 2
    warn_fallback(STATE_DIR, "DECISION_CAPTURE_STATE_DIR")
    with State(sid) as st:
        st.d["dismiss_streak"] = live_streak(st.d) + 1  # recount a stale streak before adding
        st.d.setdefault("dismissed", []).append({"at": now(), "why": why})
    print(f"dismissed: {why}")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "dismiss":
        sys.exit(cli_dismiss(sys.argv[2:]))
    if mode() == "off":
        return
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    if not inp.get("session_id"):
        return
    ev = inp.get("hook_event_name")
    if ev == "UserPromptSubmit":
        gc()
    {"UserPromptSubmit": on_user_prompt, "PostToolUse": on_post_tool_use, "Stop": on_stop}.get(ev, lambda _: None)(inp)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # a hook never fails the turn
        print(f"decision-capture: {e}", file=sys.stderr)
    sys.exit(0)
