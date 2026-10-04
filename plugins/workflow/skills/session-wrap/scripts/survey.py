#!/usr/bin/env python3
"""session-wrap survey: セッションの残件を機械で集める（判断はしない）。

  survey.py            # 現セッション（Bash の親 claude プロセス pid → claude agents --json で session_id を解決）
  survey.py --session <id>
  --json               # 機械可読

対象は起動したセッションだけ。集めるもの: cwd／git の未コミット・未追跡・未 push／現ブランチの open PR／
issue-writeback の未反映 issue。判断はしない。旗（DIRTY / UNPUSHED / PR_OPEN / PENDING_ISSUE）を立てるだけ。
"""
import argparse, json, os, subprocess, sys

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "state", "issue-writeback")

def sh(cmd, cwd=None, timeout=5):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 1, str(e)

def agents():
    rc, out = sh(["claude", "agents", "--json", "--all"], timeout=15)
    try: return json.loads(out) if rc == 0 else []
    except Exception: return []

def own_session_id(sessions):
    """Bash の祖先に居る claude プロセスの pid を agents 一覧と突き合わせる。"""
    by_pid = {str(s.get("pid")): s for s in sessions}
    p = os.getpid()
    for _ in range(12):
        rc, out = sh(["ps", "-o", "ppid=,comm=", "-p", str(p)])
        if rc != 0 or not out: return None
        ppid, comm = out.split(None, 1)
        if os.path.basename(comm.strip()) == "claude" and ppid in by_pid: return by_pid[ppid]["sessionId"]
        if str(p) in by_pid: return by_pid[str(p)]["sessionId"]
        p = int(ppid)
        if p <= 1: return None
    return None

def git_state(cwd):
    if not cwd or not os.path.isdir(cwd): return None
    rc, top = sh(["git", "rev-parse", "--show-toplevel"], cwd)
    if rc != 0: return None
    _, branch = sh(["git", "branch", "--show-current"], cwd)
    _, st = sh(["git", "status", "--porcelain"], cwd)
    lines = [l for l in st.splitlines() if l.strip()]
    untracked = sum(1 for l in lines if l.startswith("??")); dirty = len(lines) - untracked
    rc_u, ahead = sh(["git", "rev-list", "--count", "@{u}..HEAD"], cwd)
    unpushed = int(ahead) if rc_u == 0 and ahead.isdigit() else None  # None = upstream 無し
    return {"root": top, "branch": branch, "dirty": dirty, "untracked": untracked, "unpushed": unpushed}

def open_pr(cwd):
    rc, out = sh(["gh", "pr", "view", "--json", "number,url,state,reviewDecision,isDraft"], cwd, timeout=8)
    if rc != 0: return None
    try: return json.loads(out)
    except Exception: return None

def pending_issues(session_id):
    try:
        with open(os.path.join(STATE_DIR, f"{session_id}.json")) as f: d = json.load(f)
    except Exception:
        return []
    return [k for k, v in d.get("issues", {}).items() if v.get("read_at") and not v.get("written_at") and not v.get("dismissed")]

def survey(s):
    sid = s["sessionId"]; cwd = s.get("cwd") or ""
    g = git_state(cwd)
    pr = open_pr(cwd) if (g and g["branch"] not in ("", "main", "master")) else None
    pend = pending_issues(sid)
    flags = []
    if g and (g["dirty"] or g["untracked"]): flags.append("DIRTY")
    if g and g["unpushed"]: flags.append("UNPUSHED")
    if pr and pr.get("state") == "OPEN": flags.append("PR_OPEN")
    if pend: flags.append("PENDING_ISSUE")
    return {"sessionId": sid, "name": s.get("name"), "cwd": cwd, "git": g, "pr": pr, "pending_issues": pend, "flags": flags}

def fmt(r):
    head = f"{r['name'] or '(無名)'}  {r['sessionId'][:8]}"
    lines = [head, f"    cwd: {r['cwd']}"]
    g = r["git"]
    if g:
        up = "upstream無し" if g["unpushed"] is None else f"未push {g['unpushed']}"
        lines.append(f"    git: {g['branch'] or '(detached)'}  変更 {g['dirty']} / 未追跡 {g['untracked']} / {up}")
    else:
        lines.append("    git: (リポジトリ外)")
    if r["pr"]:
        p = r["pr"]; lines.append(f"    PR: #{p['number']} {p['state']} review={p.get('reviewDecision') or '-'}{' draft' if p.get('isDraft') else ''}  {p['url']}")
    if r["pending_issues"]:
        lines.append(f"    未反映 issue: {', '.join(r['pending_issues'])}")
    lines.append(f"    flags: {' '.join(r['flags']) or '(なし)'}")
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ss = agents()
    sid = a.session or own_session_id(ss)
    if not sid:
        print("session_id を特定できない（--session <id> を渡す。id は `claude agents --json`）", file=sys.stderr); sys.exit(2)
    target = next((s for s in ss if s["sessionId"] == sid), {"sessionId": sid, "cwd": os.getcwd(), "name": None})
    r = survey(target)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else fmt(r))

if __name__ == "__main__":
    main()
