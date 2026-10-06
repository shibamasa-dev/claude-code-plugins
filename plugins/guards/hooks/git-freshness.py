#!/usr/bin/env python3
"""PostToolUse hook: ローカル main の鮮度を機械的に保つ汎用ディスパッチャ。

なぜ PostToolUse か:
  PreToolUse でも permissionDecisionReason は Claude のコンテキストに乗るが、**届けるには
  ツールを止めるしかない**（additionalContext フィールドは PostToolUse 以降にしか無い）。
  merge は既に完了していて止める対象が無いので、ここは PostToolUse の additionalContext が正しい。
  逆に「古い main の上に commit する」は積む前に止めるべきなので、bash-guard.py(PreToolUse) の
  rule_main_commit_freshness が deny で担当する。**止める係=bash-guard / 知らせる係=本 hook**。

なぜ必要か（実害の記録・2026-07-16）:
  scheduler の shell ジョブは main チェックアウトの絶対パスを直に実行する
  （例: 定期ジョブ → <main のチェックアウト>/.claude/skills/.../<script>.py）。
  マージは remote で起きるためローカル main は自動追従せず、**pull するまで scheduler は
  旧コードを回し続ける**。過去の PR が「マージすれば新経路が有効」と書いたのは不正確で、
  正しくは「マージ＋ローカル pull で有効」。常駐プロセスが起動時の古いコードを回し続ける問題と同じ構造。

ルール追加＝関数を1つ書いて RULES に登録するだけ（hook の追加登録は不要）。
bash-guard.py と同じ RULES 方式に揃えてある。

現行ルール:
  1. post-merge-pull : gh pr merge / git merge の後、main が behind なら --ff-only で追従。
                       clean に通れば実行して報告、通らなければ**触らず**状況だけ注入。
                       GitHub コネクタのマージ（mcp__*__merge_pull_request）の後も同じ。
                       こちらは cwd の origin がマージした owner/repo と同じときだけ動く
                       （別リポの PR をマージしただけで手元の main を動かさない）。

設計上の約束:
  - **自動 stash はしない。** stash pop の競合で作業を黙って壊すため。ff-only が拒否したら
    状況（behind 数・未コミット変更ファイル）を注入して判断を Claude/ユーザーに返す。
  - **問題が無いときは完全に silent**（exit 0・出力なし）。毎 Bash コールで走るため。
  - 出力パースに依存せず**状態を直接見る**（tool_output のスキーマに依存しない）。
"""
import json
import os
import re
import subprocess
import sys

_CWD = None

MERGE_RE = re.compile(r"\b(gh\s+pr\s+merge\b|git\s+merge(?!-)(?!\s+--(abort|continue|quit)))")
COMMIT_RE = re.compile(r"\bgit\s+commit\b")


def inject(context: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }


def _git(args, cwd, timeout=15):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def _repo_state(cwd):
    """(branch, behind, dirty_files) を返す。判定不能なら None。"""
    r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if r.returncode != 0:
        return None
    branch = r.stdout.strip()
    # fetch は best-effort（offline なら素通り＝邪魔しない）
    _git(["fetch", "origin", "main", "--quiet"], cwd)
    r = _git(["rev-list", "--count", "HEAD..origin/main"], cwd)
    if r.returncode != 0:
        return None
    try:
        behind = int(r.stdout.strip() or "0")
    except ValueError:
        return None
    r = _git(["status", "--porcelain"], cwd)
    dirty = [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []
    return branch, behind, dirty


def _origin_slug(cwd):
    """origin の owner/repo（小文字）。GitHub でなければ None。"""
    r = _git(["config", "--get", "remote.origin.url"], cwd, timeout=5)
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


# ------------------------------------------------------------ post-merge-pull
def rule_post_merge_pull(command: str):
    if not MERGE_RE.search(command):
        return None
    return _pull_main()


def rule_post_merge_pull_mcp(tool_input: dict):
    """コネクタでマージした後。cwd が同じリポのときだけ main を追従させる。"""
    owner, repo = tool_input.get("owner"), tool_input.get("repo")
    cwd = _CWD if (_CWD and os.path.isdir(_CWD)) else None
    if not (owner and repo and cwd):
        return None
    try:
        if _origin_slug(cwd) != f"{owner}/{repo}".lower():
            return None
    except (subprocess.TimeoutExpired, OSError):
        return None
    return _pull_main()


def _pull_main():
    cwd = _CWD if (_CWD and os.path.isdir(_CWD)) else None
    if cwd is None:
        return None
    try:
        state = _repo_state(cwd)
        if state is None:
            return None
        branch, behind, dirty = state
        if branch != "main":
            return None  # main 以外に origin/main を引き込まない
        if behind == 0:
            return None  # 既に最新＝silent
        # --ff-only は衝突するローカル変更があれば自ら拒否する（勝手に壊さない）。
        # 自動 stash は絶対にしない: stash pop の競合で作業を黙って壊すため。
        r = _git(["pull", "--ff-only", "origin", "main"], cwd, timeout=60)
        if r.returncode == 0:
            return inject(
                f"[git-freshness] ローカル main を自動 pull しました（{behind} commits 追従）。"
                "scheduler の shell ジョブは main チェックアウトを直に実行するため、"
                "これでマージ済みコードが実際に live になりました。"
            )
        detail = (r.stderr or r.stdout).strip().splitlines()
        detail = detail[-1] if detail else "(理由不明)"
        files = ", ".join(l[3:] for l in dirty[:5]) or "(なし)"
        return inject(
            f"[git-freshness] ⚠️ ローカル main が origin/main より {behind} commits 遅れていますが、"
            f"自動 pull できませんでした: {detail}\n"
            f"未コミット変更 {len(dirty)} 件: {files}\n"
            "**自動 stash はしていません**（stash pop の競合で作業を壊さないため）。"
            "変更を commit するか stash するか、ユーザーに確認して判断してください。"
            "pull するまで scheduler は main チェックアウトの旧コードを回し続けます。"
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


RULES = [rule_post_merge_pull]          # Bash のコマンドを見るルール
MCP_RULES = {"merge_pull_request": rule_post_merge_pull_mcp}  # コネクタのツール名（末尾）→ ルール


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name") or ""
    global _CWD
    _CWD = data.get("cwd") or os.getcwd()
    if tool.startswith("mcp__"):
        rule = MCP_RULES.get(tool.rsplit("__", 1)[-1])
        result = rule(data.get("tool_input") or {}) if rule else None
        if result:
            print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    if tool != "Bash":
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "")
    for rule in RULES:
        result = rule(command)
        if result:
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
