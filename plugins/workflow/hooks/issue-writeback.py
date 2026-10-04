#!/usr/bin/env python3
"""issue-writeback: 「読んだ issue に決定事項を書き戻す」の強制点。

セッション内で GitHub issue を読んだ（issue_read / gh issue view）のに、その後
書いていない（issue_write update / add_issue_comment / sub_issue_write /
gh issue edit|comment|close）issue を追跡し、
  - Stop            : 未反映のまま K ターン経ったら 1 回 block して書き戻しを促す（issue ごと最大 MAX_NAGS 回）
  - UserPromptSubmit: 未反映がある間だけ 1 行リマインドを注入（無ければ無出力）
  - SessionStart    : compact/resume 後に未反映を再注入。clear 後は「未反映のまま clear された」を 1 回通知
  - SessionEnd      : clear のときだけ未反映を通知ファイルへ引き継ぐ。状態ファイルは消さない（exit→resume で同じ session_id が戻る）。掃除は GC_DAYS の mtime GC
状態は ~/.claude/state/issue-writeback/<session_id>.json（セッション単位・並行セッションは混ざらない）。
何が起きても例外で落ちず exit 0（Stop の block だけが唯一の「止める」出力）。

CLI: issue-writeback dismiss OWNER/REPO#N --session <id> [--why "..."]   # Claude が実行
     issue-writeback status [--pending]                                   # 全セッションの追跡状況（claude agents --json と突合）
"""
import fcntl, hashlib, json, os, re, sys, time
from datetime import datetime, timedelta

STATE_DIR = os.path.expanduser("~/.claude/state/issue-writeback")
K_STOPS = 3          # 読んでから（前回 nag から）この回数 Stop が来たら block
MAX_NAGS = 3         # issue ごとの block 上限（それ以降は黙る）
GC_DAYS = 30         # 古い状態ファイルの掃除（SessionEnd では消さない。resume で同じ session_id が戻ってくるため）
CLEAR_NOTICE_TTL = 600  # clear 通知の有効秒

# ---------------------------------------------------------------- state io
def _path(session_id): return os.path.join(STATE_DIR, f"{session_id}.json")

class State:
    """flock 付き read-modify-write。並列ツール呼び出しで同時に来ても壊れない。"""
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
    """(kind, ref) kind∈{read,write,None}"""
    base = tool_name.rsplit("__", 1)[-1]
    o, r, n = ti.get("owner"), ti.get("repo"), ti.get("issue_number")
    if not (o and r and n): return None, None
    ref = f"{o}/{r}#{int(n)}"
    if base == "issue_read": return "read", ref
    if base == "issue_write" and ti.get("method") == "update": return "write", ref
    if base == "add_issue_comment" and ti.get("body"): return "write", ref
    if base == "sub_issue_write": return "write", ref
    return None, None

_GH_REPO = r"(?:-R|--repo)\s+([\w.-]+/[\w.-]+)"
def refs_from_bash(cmd, cwd):
    out = []
    for seg in re.split(r"[|;&]+|\n", cmd):
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
        refs = refs_from_bash(ti.get("command", ""), inp.get("cwd", ""))
        # gh の書き込みが失敗していたら「書いた」にしない（誤って nag を抑止する方向の誤検知だけ防ぐ。read の誤検知は無害）
        tr = inp.get("tool_response") or {}
        err = (tr.get("stderr") or "") if isinstance(tr, dict) else ""
        if err and re.search(r"(?i)\b(error|failed|could not|HTTP [45]\d\d|GraphQL)\b", err):
            refs = [(k, r) for k, r in refs if k != "write"]
    elif tn.startswith("mcp__") and tn.rsplit("__", 1)[-1] in ("issue_read", "issue_write", "add_issue_comment", "sub_issue_write"):
        k, ref = refs_from_mcp(tn, ti)
        if k: refs = [(k, ref)]
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
    if not os.path.exists(_path(inp["session_id"])): return  # issue を読んでいないセッションに空ファイルを作らない
    with State(inp["session_id"]) as st:
        due = []
        for ref, it in pending(st.d).items():
            it["stops_since"] = it.get("stops_since", 0) + 1
            if it["stops_since"] >= K_STOPS and it.get("nags", 0) < MAX_NAGS:
                due.append(ref); it["stops_since"] = 0; it["nags"] = it.get("nags", 0) + 1
    if not due: return
    sid = inp["session_id"]
    lines = [f"[issue-writeback] {', '.join(due)} を読んだが、その後 issue を更新していない。"
             "この会話で決まったこと・変わった前提があるなら今すぐ反映する: "
             "現在の設計・残タスク・完了条件は body を書き換え（「今どうなっているか」）、経緯・理由はコメント（「なぜそうなったか」）。"
             "反映すべき決定が本当に無いなら、次を実行して理由を残してから終了する:"]
    for ref in due:
        lines.append(f"  issue-writeback dismiss {ref} --session {sid} --why \"<理由>\"")
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
    items = ", ".join(f"{k}（読込 {v['read_at'][11:16]}）" for k, v in p.items())
    print(f"[issue-writeback] 未反映: {items} — 決定が出たらその場で body/コメントへ（セッション終了時にまとめない）")

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
                print(f"[issue-writeback] ⚠️ 直前の会話で読んだ {', '.join(n['pending'])} が未反映のまま /clear された。"
                      "決定事項があったなら issue に載っていない可能性がある（この通知は 1 回だけ）。")
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
            hint = "要約に決定事項が残っているなら今のうちに" if reason == "compact" else "前回の会話で決めたことがあるなら続きに入る前に"
            print(f"[issue-writeback] {reason} 前に読んだ {', '.join(p)} が未反映。{hint} body/コメントへ反映する。")

def on_session_end(inp):
    """状態ファイルは残す（resume で戻ってくる）。clear だけは次の会話へ通知を引き継ぎ、状態はリセットする。"""
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
        print("--session <id> が要る（Stop の指示文に載っている）", file=sys.stderr); return 2
    with State(sid) as st:
        it = st.d["issues"].get(ref)
        if not it:
            print(f"{ref} はこのセッションの追跡対象に無い", file=sys.stderr); return 1
        it["dismissed"] = {"at": now(), "why": why}
    print(f"dismissed {ref}: {why or '(理由なし)'}"); return 0

def cli_status(argv):
    """状態ファイル × `claude agents --json --all` → セッション名・生死・未反映 issue を一覧。"""
    import subprocess
    only_pending = "--pending" in argv
    live = {}
    try:
        r = subprocess.run(["claude", "agents", "--json", "--all"], capture_output=True, text=True, timeout=10)
        live = {x["sessionId"]: x for x in json.loads(r.stdout or "[]")}
    except Exception as e:
        print(f"(claude agents を引けなかった: {e} — 生死は不明として表示)", file=sys.stderr)
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
        print("追跡中の issue なし"); return 0
    for _, sid, a, d, p in sorted(rows, key=lambda r: (r[0], r[1])):
        if a:
            head = f"● {a.get('name') or '(無名)'}  [{a.get('kind')}/{a.get('status') or '-'}]"
        else:
            head = "○ 終了済み（resume 可）"
        print(f"{head}  {sid[:8]}  {d.get('cwd') or ''}")
        for ref, it in d.get("issues", {}).items():
            st = "書き戻し済み" if it.get("written_at") else ("dismiss: " + (it["dismissed"].get("why") or "-")) if it.get("dismissed") else "★未反映"
            when = (it.get("read_at") or it.get("written_at") or "")[5:16]
            print(f"    {ref:<32} {'読込' if it.get('read_at') else '書込'} {when}  {st}")
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
    if os.path.exists(os.path.join(STATE_DIR, ".debug")):  # touch state/.debug で生入力をログ（デバッグ用）
        with open(os.path.join(STATE_DIR, ".debug.log"), "a") as f:
            f.write(json.dumps(inp, ensure_ascii=False)[:4000] + "\n")
    ev = inp.get("hook_event_name")
    {"PostToolUse": on_post_tool_use, "Stop": on_stop, "UserPromptSubmit": on_user_prompt,
     "SessionStart": on_session_start, "SessionEnd": on_session_end}.get(ev, lambda _: None)(inp)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # hook は絶対に落とさない
        print(f"issue-writeback: {e}", file=sys.stderr)
    sys.exit(0)
