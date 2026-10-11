#!/usr/bin/env python3
"""handoff: pass "where to start next time" from one session to the next.

Writer (end of session-wrap): handoff write --entry example-org/example-repo#92 --state "done up to X" --next "start with Y"
            A project can hold several. The same --entry updates, a different --entry appends (parallel sessions don't erase each other's entries).
Reader:     the SessionStart (startup/resume) hook injects every handoff of the same project (per git common dir, shared by worktrees).
            The moment the Claude that picks one up runs `handoff consume --entry <ref>`, that one entry is removed.
            --entry can be omitted when there is only one. A session opened for unrelated work does not consume, so it shows up next time too.
Check:      handoff show
No leftovers from other repos: an entry for another repo would be injected into this project's next session, where it is irrelevant.
            If --entry belongs to a different repo than the cwd's origin, it is refused (--force writes it anyway).
State:      $HANDOFF_STATE_DIR (default ~/.claude/state/handoff)/<project-key>.json (project-key = sha1 of the git common dir; cwd outside git)
            shape: {"project": root, "items": [{entry, state, next, written, at}, ...]}
"""
import hashlib, json, os, re, subprocess, sys, time
from datetime import datetime

STATE_DIR = os.path.expanduser(os.environ.get("HANDOFF_STATE_DIR", "~/.claude/state/handoff"))
STALE_DAYS = 14

def project_root(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.dirname(r.stdout.strip())
    except Exception:
        pass
    return cwd

def key_path(cwd):
    root = project_root(cwd)
    return os.path.join(STATE_DIR, hashlib.sha1(root.encode()).hexdigest()[:16] + ".json"), root

def repo_of(cwd):
    """owner/repo from the cwd's origin. None if there is no remote (= no check)."""
    try:
        r = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if r.returncode != 0: return None
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", r.stdout.strip())
    return m.group(1).lower() if m else None

def entry_repo(entry):
    """owner/repo from --entry. Only for owner/repo#N or a GitHub issue/PR URL (anything else is None = no check)."""
    m = re.match(r"^(?:https?://github\.com/)?([\w.-]+/[\w.-]+?)(?:/(?:issues|pull)/\d+|#\d+)$", entry.strip())
    return m.group(1).lower() if m else None

def load(cwd):
    """(items, path, root). items=[] if there is none."""
    p, root = key_path(cwd)
    try:
        with open(p) as f: return json.load(f)["items"], p, root
    except Exception:
        return [], p, root

def save(items, p, root):
    if not items:
        if os.path.exists(p): os.remove(p)
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump({"project": root, "items": items}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)

def render(items):
    lines = [f"[handoff] Handoffs from earlier sessions ({len(items)})"]
    for h in sorted(items, key=lambda x: x["at"], reverse=True):
        age_d = (time.time() - h["at"]) / 86400
        stale = f" (⚠️ written {age_d:.0f} days ago; its assumptions may be stale)" if age_d >= STALE_DAYS else ""
        lines += [f"- entry: {h['entry']} ({h['written'][:16]}){stale}",
                  f"  state: {h['state']}",
                  f"  next: {h['next']}"]
    lines.append("  -> If you pick one of these up, right after announcing it run "
                 "`handoff consume --entry <entry>` to remove that one. "
                 "For unrelated work, leave them (they show up in the next session too). Read the entry issue's body before starting.")
    return "\n".join(lines)

def on_session_start(inp):
    if (inp.get("reason") or inp.get("source")) not in ("startup", "resume"): return
    items, _, _ = load(inp.get("cwd") or os.getcwd())
    if items: print(render(items))

def cli(argv):
    cmd = argv[0] if argv else "show"; cwd = os.getcwd()
    opts = {}; i = 1
    while i < len(argv):
        if argv[i] == "--force": opts["force"] = True; i += 1
        elif argv[i].startswith("--") and i + 1 < len(argv): opts[argv[i][2:]] = argv[i + 1]; i += 2
        else: i += 1
    if cmd == "write":
        for k in ("entry", "state", "next"):
            if not opts.get(k): print(f"--{k} is required", file=sys.stderr); return 2
        er, cr = entry_repo(opts["entry"]), repo_of(cwd)
        if er and cr and er != cr and not opts.get("force"):
            print(f"Don't write another repo's entry to handoff (entry={er} / this project={cr}).\n"
                  "  It would be injected into this project's next session, where it is irrelevant.\n"
                  "  -> Put the leftover in an issue of that repo (issue-ops). To have it started right away, propose a waiting session (spinoff-session).\n"
                  "  -> Use --force if you really mean it", file=sys.stderr)
            return 2
        items, p, root = load(cwd)
        h = {"entry": opts["entry"], "state": opts["state"], "next": opts["next"],
             "written": datetime.now().isoformat(timespec="minutes"), "at": time.time()}
        updated = any(x["entry"] == h["entry"] for x in items)
        items = [x for x in items if x["entry"] != h["entry"]] + [h]
        save(items, p, root)
        print(f"handoff {'updated' if updated else 'added'}: {root}\n{render(items)}"); return 0
    if cmd == "consume":
        items, p, root = load(cwd)
        if not items: print(f"No handoff for this project ({root})"); return 1
        entry = opts.get("entry")
        if not entry:
            if len(items) > 1:
                print("There are several handoffs. Pass --entry for the one you are picking up:\n"
                      + "\n".join(f"  {x['entry']}" for x in items), file=sys.stderr)
                return 1
            entry = items[0]["entry"]
        if not any(x["entry"] == entry for x in items):
            print(f"No handoff for entry {entry} (available: {', '.join(x['entry'] for x in items)})", file=sys.stderr)
            return 1
        save([x for x in items if x["entry"] != entry], p, root)
        print(f"handoff consumed: {entry} ({root})"); return 0
    if cmd == "show":
        items, _, root = load(cwd)
        print(render(items) if items else f"No handoff for this project ({root})"); return 0
    print(__doc__); return 2

def main():
    if len(sys.argv) > 1:
        sys.exit(cli(sys.argv[1:]))
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    if inp.get("hook_event_name") == "SessionStart": on_session_start(inp)

if __name__ == "__main__":
    try: main()
    except Exception as e: print(f"handoff: {e}", file=sys.stderr)
    sys.exit(0)
