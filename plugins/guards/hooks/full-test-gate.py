#!/usr/bin/env python3
"""full-test-gate: 全体テストを「前回からの変更量」で促し、成果物を出す前に関門にする。

対象はリポジトリ直下に .claude/full-test.json を置いたプロジェクトだけ（無ければ何もしない）。

  {
    "command": "cd etl/database/stored_procedures && python -m pytest tests/ -q",  # 全体テスト（リポジトリ直下で実行）
    "paths": ["etl/database"],            # 変更量を数える対象パス
    "base": "origin/main",                # 既定 origin/main
    "thresholds": {"lines": 500, "commits": 10, "days": 14},   # どれかを超えたら通知
    "skipped_regex": "(\\d+) skipped",   # 出力から skip 件数を拾う（任意）
    "max_skipped": 20,                    # これを超えたら記録しない（任意）
    "gate": ["build-release\\.sh"]        # このコマンドは、前回の全体テスト以降に対象パスの変更があれば止める
  }

使い方:
  full-test-gate run      全体テストを実行し、通れば記録する。記録するのは
                          「対象パスが base と同じ内容」のときだけ（作業ブランチの結果は記録しない）。
  full-test-gate status   前回の記録と、そこからの変更量を表示
hook（stdin の hook_event_name で分岐）:
  SessionStart         しきい値を超えていたら 1 行通知（止めない）
  PreToolUse(Bash)     gate に当たるコマンドを、未検証の変更があれば deny
状態: $FULL_TEST_STATE_DIR（既定 ~/.claude/state/full-test）/<project-key>.json
      project-key = git common dir の sha1（worktree 間で共有）。形: {"sha", "at", "skipped"}
"""
import hashlib, json, os, re, subprocess, sys, time

STATE_DIR = os.path.expanduser(os.environ.get("FULL_TEST_STATE_DIR", "~/.claude/state/full-test"))
DEFAULT_THRESHOLDS = {"lines": 500, "commits": 10, "days": 14}


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=20)
    return r.returncode, r.stdout.strip()


def load_project(cwd):
    """(config, toplevel, state_path)。対象外なら (None, None, None)。"""
    rc, top = git(cwd, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None, None, None
    try:
        with open(os.path.join(top, ".claude", "full-test.json")) as f:
            cfg = json.load(f)
    except Exception:
        return None, None, None
    _, common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    key = hashlib.sha1(common.encode()).hexdigest()[:16]
    return cfg, top, os.path.join(STATE_DIR, key + ".json")


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def measure(top, cfg, sha, target):
    """sha から target（ref。None なら作業ツリー）までの対象パスの変更量。"""
    paths = cfg.get("paths") or ["."]
    rng = [sha, target] if target else [sha]
    _, stat = git(top, "diff", "--shortstat", *rng, "--", *paths)
    nums = {k: int(v) for v, k in re.findall(r"(\d+) (file|insertion|deletion)", stat)}
    commits = 0
    if target:
        _, c = git(top, "rev-list", "--count", f"{sha}..{target}", "--", *paths)
        commits = int(c or 0)
    return {"files": nums.get("file", 0),
            "lines": nums.get("insertion", 0) + nums.get("deletion", 0),
            "commits": commits}


def describe(state, m):
    days = int((time.time() - state["at"]) // 86400)
    return (f"前回の全体テスト（{time.strftime('%Y-%m-%d', time.localtime(state['at']))}・{state['sha'][:8]}）から "
            f"{m['lines']} 行 / {m['files']} ファイル / {m['commits']} コミット / {days} 日"), days


def cmd_status(cwd):
    cfg, top, sp = load_project(cwd)
    if not cfg:
        print("対象外（.claude/full-test.json が無い）"); return 0
    state = load_state(sp)
    if not state:
        print("全体テストの記録なし。full-test-gate run"); return 0
    text, _ = describe(state, measure(top, cfg, state["sha"], cfg.get("base", "origin/main")))
    print(text + f"（skip {state.get('skipped')}）")
    return 0


def cmd_run(cwd):
    cfg, top, sp = load_project(cwd)
    if not cfg:
        print("対象外（.claude/full-test.json が無い）"); return 1
    base, paths = cfg.get("base", "origin/main"), cfg.get("paths") or ["."]
    rc_same, _ = git(top, "diff", "--quiet", base, "--", *paths)
    p = subprocess.Popen(cfg["command"], shell=True, cwd=top, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    out = []
    for line in p.stdout:
        sys.stdout.write(line); out.append(line)
    if p.wait() != 0:
        print(f"[full-test-gate] 失敗（exit {p.returncode}）。記録しない"); return p.returncode
    skipped = None
    if cfg.get("skipped_regex"):
        found = re.findall(cfg["skipped_regex"], "".join(out))
        skipped = int(found[-1]) if found else 0
    if skipped is not None and cfg.get("max_skipped") is not None and skipped > cfg["max_skipped"]:
        print(f"[full-test-gate] skip {skipped} 件 > 上限 {cfg['max_skipped']}。記録しない（実サンプル等の前提を確認）")
        return 1
    if rc_same != 0:
        print(f"[full-test-gate] 成功。ただし対象パスが {base} と違うので記録しない（作業中の変更の結果）")
        return 0
    _, sha = git(top, "rev-parse", base)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(sp, "w") as f:
        json.dump({"sha": sha, "at": time.time(), "skipped": skipped}, f)
    print(f"[full-test-gate] 記録した: {base} {sha[:8]}（skip {skipped}）")
    return 0


def hook_session_start(cwd):
    cfg, top, sp = load_project(cwd)
    if not cfg:
        return
    state = load_state(sp)
    if not state:
        print("[full-test] 全体テストの記録がありません。main の状態で "
              "`full-test-gate run` を 1 回実行すると、以後は変更量で通知します。")
        return
    m = measure(top, cfg, state["sha"], cfg.get("base", "origin/main"))
    text, days = describe(state, m)
    th = {**DEFAULT_THRESHOLDS, **(cfg.get("thresholds") or {})}
    over = [k for k, v in (("lines", m["lines"]), ("commits", m["commits"])) if v >= th[k]]
    if m["lines"] and days >= th["days"]:
        over.append("days")
    if over:
        print(f"[full-test] 全体テストの時期です。{text}（しきい値超過: {', '.join(over)}）。"
              "作業の切れ目に main で `full-test-gate run` を実行してください。")


def hook_pre_bash(cwd, command):
    cfg, top, sp = load_project(cwd)
    if not cfg or not any(re.search(g, command) for g in cfg.get("gate") or []):
        return
    state = load_state(sp)
    if state:
        m = measure(top, cfg, state["sha"], None)
        if m["lines"] == 0:
            return
        reason = (f"全体テスト未実施の変更があります（前回 {state['sha'][:8]} から対象パスで {m['lines']} 行 / "
                  f"{m['files']} ファイル）。")
    else:
        reason = "全体テストの記録がありません。"
    reason += " 先に main の状態で `full-test-gate run` を通してください。"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": "[full-test] " + reason}},
                     ensure_ascii=False))


def main():
    if len(sys.argv) > 1:
        return {"run": cmd_run, "status": cmd_status}[sys.argv[1]](os.getcwd())
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cwd = data.get("cwd") or os.getcwd()
    try:
        if data.get("hook_event_name") == "SessionStart":
            hook_session_start(cwd)
        elif data.get("hook_event_name") == "PreToolUse" and data.get("tool_name") == "Bash":
            hook_pre_bash(cwd, (data.get("tool_input") or {}).get("command", ""))
    except Exception:
        pass  # hook は作業を止めない
    return 0


if __name__ == "__main__":
    sys.exit(main())
