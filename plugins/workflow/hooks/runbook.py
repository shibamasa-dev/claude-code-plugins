#!/usr/bin/env python3
"""runbook: enforces leaving a runbook for computer use / browser use procedures.

The hook records the raw log mechanically; Claude writes the runbook (runbook.md) at the end of the work. Forgetting it is stopped at Stop.
  - PostToolUse  (hook-post)          : append calls of the target tools to <root>/_inbox/<sid>.jsonl (a batch is expanded to one line per action).
                                        Only whitelisted keys are kept; any other string or number keeps only its length
                                        (type text, form_input values, javascript code and passwords leave not a single character)
                                        On a session's first operation, print additionalContext on how to record it (start gif_creator, or note key steps)
  - Stop         (hook-stop)          : if the inbox has at least OP_MIN operation steps and it was not finished with new/use/dismiss,
                                        block every K_STOPS Stops (at most MAX_NAGS times per batch of work until it is finished)
  - SessionStart (hook-session-start) : sweep --apply once a day. Print one line only when something was deleted
Storage <root> = $RUNBOOK_ROOT or ~/.claude/runbooks
  _inbox/<sid>.jsonl   raw log before it is finished (the hook doesn't know the task name)
  _state/<sid>.json    the Stop nag counter and the finish record
  <YYYY-MM-DD>_<slug>/ runbook.md + steps.jsonl (later runs go to steps-<date>.jsonl)
Whatever happens the hook never raises and exits 0 (the Stop block is the only output that stops anything).

CLI (run by Claude as python3 "<plugin root>/hooks/runbook.py" <subcommand>; the Stop message prints the full path):
  new --session <id> --slug <task-name> --recurrence once|monthly|yearly [--title ...] [--gif <path>]
  use <dir> --session <id>
  dismiss --session <id> --why "..."
  promote <dir> --skill <skill directory>
  sweep [--apply]
  list
"""
import argparse, fcntl, json, os, re, shutil, subprocess, sys, time
from datetime import date, datetime, timedelta

ROOT = os.path.expanduser(os.environ.get("RUNBOOK_ROOT") or "~/.claude/runbooks")
INBOX = os.path.join(ROOT, "_inbox")
STATE_DIR = os.path.join(ROOT, "_state")
SELF = f'python3 "{os.path.abspath(__file__)}"'  # how messages tell Claude to run this script
K_STOPS = 3            # block after this many Stops once operations reach OP_MIN (or since the last nag)
MAX_NAGS = 3           # max blocks per batch of work until it is finished (reset by new/use/dismiss)
OP_MIN = 3             # sessions with fewer operations than this are not stopped
INBOX_GC_DAYS = 14     # inbox logs left unfinished
STATE_GC_DAYS = 30
GIF_MV_TIMEOUT = 10    # reads/writes in ~/Downloads can hang on some hosts
KEEP_DAYS = {"once": ("created", 60), "monthly": ("last_used", 45), "yearly": ("last_used", 400)}
FM_KEYS = ["title", "created", "last_used", "uses", "recurrence", "keep_until", "status", "sessions", "gif"]
DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_.+")
SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
TOOL_RE = re.compile(r"^mcp__(claude-in-chrome|computer-use|remote-devices|Claude_Browser)__")  # Playwright is out of scope

# ------------------------------------------------------------ step recording
# Keys we may keep (value as is). Other strings and numbers keep only their length; IGNORE is dropped
KEEP = {"action", "ref", "ref_id", "element_index", "query", "label", "app", "window_id", "filter",
        "coordinate", "start_coordinate", "to_coordinate", "region", "scroll_direction"}
IGNORE = {"tabId", "tabIds", "serverId", "deviceId", "scale", "duration", "scroll_amount", "repeat", "max_chars",
          "depth", "limit", "save_to_disk", "force", "width", "height", "preset", "colorScheme", "count", "dx", "dy",
          "foreground", "onlyErrors", "createIfEmpty", "pattern", "urlPattern", "requestId", "lines", "options", "download"}
# Classification (decided here only): anything that can change the screen or state is an "operation", the rest is a "read"
OP_ACTIONS = {"left_click", "right_click", "middle_click", "double_click", "triple_click", "click", "type", "key",
              "scroll", "left_click_drag", "drag", "left_mouse_down", "left_mouse_up"}
OP_TOOLS = {"navigate", "form_input", "file_upload", "upload_image", "javascript_tool", "shortcuts_execute",
            "autofill_credential", "open_application", "app_click", "app_scroll", "write_clipboard"}
SHOT = {"screenshot", "zoom", "app_screenshot", "app_zoom"}

def now(): return datetime.now().isoformat(timespec="seconds")
def today(): return date.today()
def valid_sid(s): return isinstance(s, str) and bool(SID_RE.match(s))
def inbox_path(sid): return os.path.join(INBOX, f"{sid}.jsonl")

def clean_url(u):
    """Drop the query string, fragment and userinfo. For javascript:/data: drop the contents."""
    if not isinstance(u, str): return None
    s = u.strip()
    m = re.match(r"(?i)^(javascript|data):", s)
    if m: return f"{m.group(0)}<{len(s)} chars>"
    s = re.sub(r"^([A-Za-z][A-Za-z0-9+.-]*://)?[^/@]*@", r"\1", s)
    return s.split("#", 1)[0].split("?", 1)[0]

def _plain(v):
    return isinstance(v, (str, int, float, bool)) or (isinstance(v, list) and all(isinstance(x, (int, float)) for x in v))

def _step(tool, base, ti, sub=None, app=None):
    act = ti.get("action") if isinstance(ti.get("action"), str) else None
    st = {"t": now(), "tool": tool}
    if sub: st["sub"] = sub
    if act: st["action"] = act
    if app and "app" not in ti: st["app"] = app
    masked = {}
    for k, v in ti.items():
        if k == "action" or k in IGNORE: continue
        if k == "url":
            cu = clean_url(v)
            if cu is not None: st["url"] = cu
        elif base == "app_menu" and k in ("path", "list") and isinstance(v, (str, list)):
            st["label"] = " > ".join(map(str, v)) if isinstance(v, list) else v
        elif k in KEEP and _plain(v):
            st[k] = v
        elif isinstance(v, (str, int, float, bool)):
            masked[k] = len(str(v))
        elif isinstance(v, (dict, list)):
            masked[k] = len(json.dumps(v, ensure_ascii=False))
    if masked: st["masked"] = masked
    st["kind"] = "op" if (act in OP_ACTIONS or base in OP_TOOLS or (base == "app_menu" and "path" in ti)) else "read"
    st["shot"] = bool(act in SHOT or base in SHOT or ti.get("save_to_disk") is True)
    return st

def steps_from(tool, ti):
    base = tool.rsplit("__", 1)[-1]
    acts = ti.get("actions")
    if not isinstance(acts, list):
        return [_step(tool, base, ti)]
    app = ti.get("app") if isinstance(ti.get("app"), str) else None
    out = []
    for a in acts:
        if not isinstance(a, dict): continue
        if isinstance(a.get("name"), str) and isinstance(a.get("input"), dict):   # browser_batch: {name, input}
            out.append(_step(tool, a["name"].rsplit("__", 1)[-1], a["input"], sub=a["name"], app=app))
        else:                                                                     # computer_batch / app_batch: flat
            out.append(_step(tool, base, a, app=app))
    return out

def count_steps(path):
    n_all = n_op = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try: d = json.loads(line)
                except Exception: continue
                if isinstance(d, dict): n_all += 1; n_op += d.get("kind") == "op"
    except FileNotFoundError:
        pass
    return n_all, n_op

# ---------------------------------------------------------------- state io
class State:
    """Read-modify-write under flock. Safe when hooks / CLI calls run in parallel."""
    def __init__(self, sid):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.p = os.path.join(STATE_DIR, f"{sid}.json"); self.lock = self.p + ".lock"
    def __enter__(self):
        self.lf = open(self.lock, "w"); fcntl.flock(self.lf, fcntl.LOCK_EX)
        try:
            with open(self.p) as f: self.d = json.load(f)
        except Exception:
            self.d = {}
        self.d.setdefault("stops_since", 0); self.d.setdefault("nags", 0); self.d.setdefault("log", [])
        return self
    def __exit__(self, *a):
        tmp = self.p + ".tmp"
        with open(tmp, "w") as f: json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p)
        fcntl.flock(self.lf, fcntl.LOCK_UN); self.lf.close()

def finalize(sid, rec):
    """Common post-processing for new/use/dismiss: reset the nag counter and record what was done."""
    with State(sid) as st:
        st.d["stops_since"] = 0; st.d["nags"] = 0
        st.d["log"].append(dict(rec, at=now()))

# ------------------------------------------------------------- frontmatter
def read_fm(path):
    try:
        with open(path, encoding="utf-8") as f: text = f.read()
    except Exception:
        return None, None
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m: return None, None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line: continue
        k, v = line.split(":", 1); k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]
        elif v.startswith("[") and v.endswith("]"): v = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
        elif v in ("", "null", "~"): v = None
        fm[k] = v
    return fm, text[m.end():]

def dump_fm(fm):
    lines = ["---"]
    for k in FM_KEYS:
        v = fm.get(k)
        if isinstance(v, list): s = "[" + ", ".join(v) + "]"
        elif v is None: s = "null"
        elif k in ("title", "gif"): s = '"' + str(v).replace("\n", " ") + '"'
        else: s = str(v)
        lines.append(f"{k}: {s}")
    return "\n".join(lines + ["---"]) + "\n"

def write_runbook(path, fm, body):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(dump_fm(fm) + body)
    os.replace(tmp, path)

def pdate(s):
    try: return date.fromisoformat(str(s))
    except Exception: return None

def calc_keep(fm):
    key, days = KEEP_DAYS[fm["recurrence"]]
    return ((pdate(fm.get(key)) or today()) + timedelta(days=days)).isoformat()

BODY = """
# {title}

## Goal

## Prerequisites and inputs (no secrets: for passwords, PINs and transaction passwords write only "entered by the user")

## Steps (screen names, button labels, values entered; no coordinates)

## Branches and pitfalls

## Stop points (approval boundaries: right before paying, sending, confirming, etc.)

## Verification (where completion was confirmed)

## Recording

{rec}
"""

# ------------------------------------------------------------------ events
def on_post(inp):
    tool = inp.get("tool_name")
    sid = inp.get("session_id")
    if not isinstance(tool, str) or not TOOL_RE.match(tool) or not valid_sid(sid): return
    ti = inp.get("tool_input")
    steps = steps_from(tool, ti if isinstance(ti, dict) else {})
    if not steps: return
    os.makedirs(INBOX, exist_ok=True)
    with open(inbox_path(sid), "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        first = os.fstat(f.fileno()).st_size == 0   # read under the lock: a concurrent first write may have just landed
        f.write("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in steps))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)
    if first: print_record_hint(tool)

def print_record_hint(tool):
    """On the first operation of a session, say how to capture it: a Stop-time reminder is too late to start a recording."""
    if tool.endswith("__gif_creator"): return   # already recording
    if tool.startswith("mcp__claude-in-chrome__"):
        hint = ("[runbook] Browser operations are being logged for a runbook. Start a recording now with "
                "mcp__claude-in-chrome__gif_creator (start_recording) and attach the GIF with --gif when you run `new`.")
    else:
        hint = ("[runbook] Operations are being logged for a runbook. This tool cannot record a GIF, "
                "so note the key steps as you go and write them into runbook.md.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": hint}}, ensure_ascii=False))

def on_stop(inp):
    if inp.get("stop_hook_active"): return
    sid = inp.get("session_id")
    if not valid_sid(sid) or not os.path.exists(inbox_path(sid)): return  # don't create state for a session that never touched a browser
    n_all, n_op = count_steps(inbox_path(sid))
    if n_op < OP_MIN: return
    with State(sid) as st:
        st.d["stops_since"] += 1
        if st.d["stops_since"] < K_STOPS or st.d["nags"] >= MAX_NAGS: return
        st.d["stops_since"] = 0; st.d["nags"] += 1
    reason = "\n".join([
        f"[runbook] This session made {n_op} computer use / browser use operations"
        f" ({n_all} log entries recorded automatically, input values masked) but has not turned them into a runbook yet. Run one of these before ending:",
        f"  new procedure:                   {SELF} new --session {sid} --slug <task-name> --recurrence once|monthly|yearly --title \"<title>\" [--gif <path to recorded GIF>]",
        f"  rerun of an existing runbook:    {SELF} use <folder (find it with {SELF} list)> --session {sid}",
        f"  nothing to record (just checks): {SELF} dismiss --session {sid} --why \"<reason>\"",
        "After new / use, fill each heading of runbook.md from steps.jsonl and the conversation (for passwords and PINs write only \"entered by the user\")."])
    print(json.dumps({"decision": "block", "reason": reason,
                      "hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": reason}}, ensure_ascii=False))

def on_session_start(inp):
    """Clean up only once a day (dozens of sessions start per day, so only the first one sweeps and reports)."""
    os.makedirs(ROOT, exist_ok=True)
    with open(os.path.join(ROOT, ".sweep.lock"), "w") as lf:
        try: fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError: return   # another session started at the same time is sweeping
        marker = os.path.join(ROOT, ".last_sweep")
        try:
            with open(marker) as f: last = f.read().strip()
        except Exception:
            last = ""
        if last == today().isoformat(): return
        with open(marker, "w") as f: f.write(today().isoformat())  # write first (if the sweep crashes, don't retry every session)
        rb, ib, _ = sweep(apply=True)
    parts = []
    if rb: parts.append(f"deleted {len(rb)} expired ({', '.join(rb[:3])}{', ...' if len(rb) > 3 else ''})")
    if ib: parts.append(f"deleted {len(ib)} unfinished inbox log(s)")
    if parts: print("runbooks: " + " / ".join(parts))

# ------------------------------------------------------------------- sweep
def sweep(apply):
    """Return (runbooks, inbox files, state files) to delete. Deletes them only with apply."""
    rb, ib, stf = [], [], []
    t = today()
    try: names = sorted(os.listdir(ROOT))
    except FileNotFoundError: names = []
    for n in names:
        d = os.path.join(ROOT, n)
        if not DIR_RE.match(n) or os.path.islink(d) or not os.path.isdir(d): continue
        fm, _ = read_fm(os.path.join(d, "runbook.md"))
        ku = pdate(fm.get("keep_until")) if fm else None
        if fm and fm.get("status") == "draft" and ku and ku < t:   # keep unreadable ones and anything not draft
            rb.append(n)
    for dirpath, days, out in ((INBOX, INBOX_GC_DAYS, ib), (STATE_DIR, STATE_GC_DAYS, stf)):
        cutoff = time.time() - days * 86400
        try:
            for n in sorted(os.listdir(dirpath)):
                fp = os.path.join(dirpath, n)
                if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff: out.append(n)
        except FileNotFoundError:
            pass
    if apply:
        for n in rb: shutil.rmtree(os.path.join(ROOT, n), ignore_errors=True)
        for dirpath, out in ((INBOX, ib), (STATE_DIR, stf)):
            for n in out:
                try: os.remove(os.path.join(dirpath, n))
                except Exception: pass
    return rb, ib, stf

# --------------------------------------------------------------------- cli
def err(msg):
    print(msg, file=sys.stderr); return 1

def resolve_dir(arg):
    """Accept only <YYYY-MM-DD>_<slug> directly under root that holds runbook.md (so nothing else gets deleted by mistake)."""
    p = os.path.expanduser(arg)
    if not os.path.isabs(p): p = os.path.join(ROOT, p)
    p = os.path.realpath(p)
    if os.path.dirname(p) != os.path.realpath(ROOT) or not DIR_RE.match(os.path.basename(p)): return None
    return p if os.path.isfile(os.path.join(p, "runbook.md")) else None

def move_inbox(sid, dst):
    """Move this session's inbox to dst (append if it exists). Returns (all, operations); (0, 0) if there is no inbox."""
    src = inbox_path(sid)
    if not os.path.exists(src): return 0, 0
    n = count_steps(src)
    if os.path.exists(dst):
        with open(src, encoding="utf-8") as s, open(dst, "a", encoding="utf-8") as d: d.write(s.read())
        os.remove(src)
    else:
        os.replace(src, dst)
    return n

def move_gif(src, d):
    """mv the GIF into the runbook folder. On a hang or failure return the original path (no in-process stat either)."""
    src = os.path.abspath(os.path.expanduser(src))
    try:
        p = subprocess.Popen(["mv", src, d + "/"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return src, f"cannot start mv: {e}"
    try:
        rc = p.wait(timeout=GIF_MV_TIMEOUT)
    except subprocess.TimeoutExpired:
        p.kill()
        try: p.wait(timeout=2)
        except Exception: pass
        return src, f"mv did not finish within {GIF_MV_TIMEOUT} seconds"
    if rc != 0: return src, f"mv failed (exit {rc})"
    return os.path.join(d, os.path.basename(src)), None

def cli_new(a):
    if not valid_sid(a.session): return err("invalid --session")
    slug = re.sub(r"[\s/\\:]+", "-", a.slug).strip("-.")
    if not slug: return err("--slug is empty")
    t = today().isoformat()
    d = os.path.join(ROOT, f"{t}_{slug}")
    if os.path.exists(d): return err(f"{d} already exists. For a rerun of the same task use `use`")
    os.makedirs(d)
    n_all, n_op = move_inbox(a.session, os.path.join(d, "steps.jsonl"))
    if not n_all: open(os.path.join(d, "steps.jsonl"), "a").close()
    gif, gif_err = move_gif(a.gif, d) if a.gif else (None, None)
    title = a.title or slug
    fm = {"title": title, "created": t, "last_used": t, "uses": 1, "recurrence": a.recurrence,
          "keep_until": None, "status": "draft", "sessions": [a.session], "gif": gif}
    fm["keep_until"] = calc_keep(fm)
    rec = ("- none (computer use cannot record; write only the key points in the steps)" if not gif else
           f"- GIF (could not be moved, still at its original place): {gif}" if gif_err else f"- GIF: {gif}")
    write_runbook(os.path.join(d, "runbook.md"), fm, BODY.format(title=title, rec=rec + "\n- raw log: steps.jsonl (input values masked)"))
    finalize(a.session, {"how": "new", "dir": d, "steps": n_all})
    print(d)
    print(f"  steps.jsonl: {n_all} entries ({n_op} operations) / keep_until: {fm['keep_until']} ({a.recurrence})")
    if not n_all: print("  ⚠️ this session had no inbox (steps.jsonl is empty)")
    if gif_err: print(f"  ⚠️ could not move the GIF ({gif_err}). Recorded the original path in the frontmatter gif:")
    print("Next: fill each heading of runbook.md from steps.jsonl and the conversation (for passwords and PINs write only \"entered by the user\")")
    return 0

def cli_use(a):
    if not valid_sid(a.session): return err("invalid --session")
    d = resolve_dir(a.dir)
    if not d: return err(f"{a.dir} is not a runbook folder (find it with {SELF} list)")
    rb = os.path.join(d, "runbook.md")
    fm, body = read_fm(rb)
    if not fm or fm.get("recurrence") not in KEEP_DAYS: return err(f"cannot read the frontmatter of {rb}")
    t = today().isoformat()
    n_all, n_op = move_inbox(a.session, os.path.join(d, f"steps-{t}.jsonl"))
    try: fm["uses"] = int(fm.get("uses") or 1) + 1
    except ValueError: fm["uses"] = 2
    fm["last_used"] = t
    ss = fm.get("sessions")
    ss = ss if isinstance(ss, list) else ([ss] if ss else [])
    fm["sessions"] = [s for s in ss if s != a.session] + [a.session]
    old = pdate(fm.get("keep_until"))
    new = calc_keep(fm)
    fm["keep_until"] = max(old.isoformat(), new) if old else new
    write_runbook(rb, fm, body)
    finalize(a.session, {"how": "use", "dir": d, "steps": n_all})
    print(d)
    print(f"  steps-{t}.jsonl: {n_all} entries ({n_op} operations) / uses: {fm['uses']} / keep_until: {fm['keep_until']}")
    if not n_all: print("  ⚠️ this session had no inbox (no log for this run)")
    if fm["uses"] >= 2:
        print(f"Run #{fm['uses']}. Propose turning it into a skill (give runbook.md to skill-creator)")
    return 0

def cli_dismiss(a):
    if not valid_sid(a.session): return err("invalid --session")
    if not a.why.strip(): return err("give a reason in --why")
    n_all, _ = count_steps(inbox_path(a.session))
    try: os.remove(inbox_path(a.session))
    except FileNotFoundError: pass
    finalize(a.session, {"how": "dismiss", "why": a.why, "steps": n_all})
    print(f"dismissed: discarded {n_all} log entries (reason: {a.why})")
    return 0

def cli_promote(a):
    d = resolve_dir(a.dir)
    if not d: return err(f"{a.dir} is not a runbook folder. Nothing was deleted")
    skill = os.path.realpath(os.path.expanduser(a.skill))
    if not os.path.isfile(os.path.join(skill, "SKILL.md")): return err(f"{skill}/SKILL.md does not exist. Nothing was deleted")
    if skill == d or skill.startswith(d + os.sep): return err("the skill is inside the runbook folder. Nothing was deleted")
    shutil.rmtree(d)
    print(f"promoted: deleted {os.path.basename(d)} (from now on the source of truth is {skill})")
    return 0

def cli_sweep(a):
    rb, ib, stf = sweep(apply=a.apply)
    tag = "deleted" if a.apply else "[dry-run] would delete"
    print(f"{tag}: {len(rb)} expired draft(s) / {len(ib)} unfinished inbox log(s) (older than {INBOX_GC_DAYS} days) / {len(stf)} old state file(s)")
    for n in rb: print(f"  runbook  {n}")
    for n in ib: print(f"  inbox    {n}")
    if not a.apply and (rb or ib or stf): print("run with --apply to delete")
    return 0

def cli_list(a):
    rows = []
    try: names = sorted(os.listdir(ROOT))
    except FileNotFoundError: names = []
    for n in names:
        if not DIR_RE.match(n) or not os.path.isdir(os.path.join(ROOT, n)): continue
        fm, _ = read_fm(os.path.join(ROOT, n, "runbook.md"))
        if not fm: rows.append((n, "(frontmatter unreadable)", "-", "-", "-", "-")); continue
        rows.append((n, fm.get("title") or "", fm.get("status") or "-", str(fm.get("uses") or "-"),
                     fm.get("last_used") or "-", fm.get("keep_until") or "-"))
    if not rows: print("no runbooks")
    for n, title, status, uses, last, keep in rows:
        print(f"{n}\n    {title}  status={status} uses={uses} last_used={last} keep_until={keep}")
    try: pend = [x for x in os.listdir(INBOX) if x.endswith(".jsonl")]
    except FileNotFoundError: pend = []
    if pend: print(f"(unfinished inbox: {len(pend)} session(s))")
    return 0

def cli(argv):
    ap = argparse.ArgumentParser(prog="runbook.py")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new"); p.add_argument("--session", required=True); p.add_argument("--slug", required=True)
    p.add_argument("--recurrence", required=True, choices=list(KEEP_DAYS)); p.add_argument("--title"); p.add_argument("--gif")
    p.set_defaults(fn=cli_new)
    p = sp.add_parser("use"); p.add_argument("dir"); p.add_argument("--session", required=True); p.set_defaults(fn=cli_use)
    p = sp.add_parser("dismiss"); p.add_argument("--session", required=True); p.add_argument("--why", required=True)
    p.set_defaults(fn=cli_dismiss)
    p = sp.add_parser("promote"); p.add_argument("dir"); p.add_argument("--skill", required=True); p.set_defaults(fn=cli_promote)
    p = sp.add_parser("sweep"); p.add_argument("--apply", action="store_true"); p.set_defaults(fn=cli_sweep)
    p = sp.add_parser("list"); p.set_defaults(fn=cli_list)
    a = ap.parse_args(argv)
    return a.fn(a)

HOOKS = {"hook-post": on_post, "hook-stop": on_stop, "hook-session-start": on_session_start}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in HOOKS:
        sys.exit(cli(sys.argv[1:]))
    try:
        inp = json.load(sys.stdin)
    except Exception:
        inp = None
    if isinstance(inp, dict) or cmd == "hook-session-start":
        try:
            HOOKS[cmd](inp if isinstance(inp, dict) else {})
        except Exception as e:  # a hook must never crash
            print(f"runbook: {e}", file=sys.stderr)
    sys.exit(0)

if __name__ == "__main__":
    main()
