#!/usr/bin/env python3
"""handoff: セッションをまたぐ「次回の入口」の受け渡し。

書く側（session-wrap の最後）: handoff write --entry example-org/example-repo#92 --state "○○まで済み" --next "まず △△"
            1 プロジェクトに複数件持てる。同じ --entry なら更新、別の --entry なら追記（並行セッションが互いの入口を消さない）。
受け取る側: SessionStart(startup/resume) hook が同じプロジェクト（git common dir 単位・worktree 共有）の handoff を全件注入する。
            着手する Claude が `handoff consume --entry <ref>` を実行した瞬間にその 1 件が消える。
            1 件しか無いときは --entry を省略できる。無関係な作業で開いたセッションは consume しない → 次のセッションにも出る。
確認: handoff show
別リポの残件は書かない: 他リポの入口を書くと、このプロジェクトの次のセッションに無関係な入口が注入される。
            --entry が現 cwd の origin と別リポなら拒否する（--force で書ける）。
状態: $HANDOFF_STATE_DIR（既定 ~/.claude/state/handoff）/<project-key>.json（project-key = git common dir の sha1。git 外は cwd）
            形: {"project": root, "items": [{entry, state, next, written, at}, ...]}
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
    """cwd の origin から owner/repo。remote が無ければ None（＝チェックしない）。"""
    try:
        r = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if r.returncode != 0: return None
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", r.stdout.strip())
    return m.group(1).lower() if m else None

def entry_repo(entry):
    """--entry から owner/repo。owner/repo#N か GitHub の issue/PR URL のときだけ（他は None＝チェックしない）。"""
    m = re.match(r"^(?:https?://github\.com/)?([\w.-]+/[\w.-]+?)(?:/(?:issues|pull)/\d+|#\d+)$", entry.strip())
    return m.group(1).lower() if m else None

def load(cwd):
    """(items, path, root)。無ければ items=[]。"""
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
    lines = [f"[handoff] 前回までのセッションからの引き継ぎ（{len(items)} 件）"]
    for h in sorted(items, key=lambda x: x["at"], reverse=True):
        age_d = (time.time() - h["at"]) / 86400
        stale = f"（⚠️ {age_d:.0f} 日前の引き継ぎ。前提が古い可能性あり）" if age_d >= STALE_DAYS else ""
        lines += [f"- 入口: {h['entry']}（{h['written'][:16]}）{stale}",
                  f"  状態: {h['state']}",
                  f"  次にやること: {h['next']}"]
    lines.append("  → どれかの続きに着手するなら、着手を宣言した直後に "
                 "`handoff consume --entry <入口>` を実行してその 1 件を消す。"
                 "無関係な作業ならそのまま（次のセッションにも出る）。入口 issue の body を読んでから始める。")
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
            if not opts.get(k): print(f"--{k} が要る", file=sys.stderr); return 2
        er, cr = entry_repo(opts["entry"]), repo_of(cwd)
        if er and cr and er != cr and not opts.get("force"):
            print(f"別リポの入口は handoff に書かない（entry={er} / このプロジェクト={cr}）。\n"
                  "  書くと、このプロジェクトの次のセッションに無関係な入口が注入される。\n"
                  "  → 残件は対象リポの issue に落とす（issue-ops）。すぐ着手させたいなら spinoff-session の待機セッションを提案する。\n"
                  "  → 意図して書くなら --force", file=sys.stderr)
            return 2
        items, p, root = load(cwd)
        h = {"entry": opts["entry"], "state": opts["state"], "next": opts["next"],
             "written": datetime.now().isoformat(timespec="minutes"), "at": time.time()}
        updated = any(x["entry"] == h["entry"] for x in items)
        items = [x for x in items if x["entry"] != h["entry"]] + [h]
        save(items, p, root)
        print(f"handoff {'更新' if updated else '追記'}: {root}\n{render(items)}"); return 0
    if cmd == "consume":
        items, p, root = load(cwd)
        if not items: print(f"このプロジェクト（{root}）に handoff は無い"); return 1
        entry = opts.get("entry")
        if not entry:
            if len(items) > 1:
                print("handoff が複数ある。--entry で着手する 1 件を指定する:\n"
                      + "\n".join(f"  {x['entry']}" for x in items), file=sys.stderr)
                return 1
            entry = items[0]["entry"]
        if not any(x["entry"] == entry for x in items):
            print(f"入口 {entry} の handoff は無い（あるのは: {', '.join(x['entry'] for x in items)}）", file=sys.stderr)
            return 1
        save([x for x in items if x["entry"] != entry], p, root)
        print(f"handoff 消費: {entry}（{root}）"); return 0
    if cmd == "show":
        items, _, root = load(cwd)
        print(render(items) if items else f"このプロジェクト（{root}）に handoff は無い"); return 0
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
