#!/usr/bin/env python3
"""PostToolUse hook: DESIGN.md を編集したら lint を走らせ、指摘があれば注入して直させる。

matcher は "Edit|Write"（**ツール名しかマッチできない**ので、パスでは絞れない）。
DESIGN.md 以外のファイルは basename で弾いて即 exit する＝出力ゼロ・完全に silent。
つまり全編集で python3 が1回起動するが、対象外は数十 ms で抜ける。

なぜ pre-commit でなくここか（2026-09-10 判断）:
  commit ゲートより、編集した直後のセッション内で直せるほうが早い。
  pre-commit は「ユーザーの手編集も捕まえる」利点があるが、今回はそちらを採らない。

なぜ @latest か:
  ユーザーの明示指示（「@google/design.md は最新版にしてね」）。実測で @latest は約4.2秒・
  ネット必須、@0.4.0 固定なら約2.2秒・オフライン可。alpha ツールなので破壊的変更で
  ここが落ちる可能性がある。固定に切り替えるなら CMD の版指定を変えるだけ。

lint が落ちた場合（ネット断・npx 失敗）は**黙って通さない** — 検証できなかったことを
明示して注入する。silent pass は「lint 済み」と誤認させるため。
"""
import json
import os
import subprocess
import sys

TARGET = "DESIGN.md"
CMD = ["npx", "-y", "@google/design.md@latest", "lint"]
TIMEOUT = 45


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not str(data.get("tool_name", "")).endswith(("Edit", "Write")):
        sys.exit(0)

    path = (data.get("tool_input") or {}).get("file_path") or ""
    if os.path.basename(path) != TARGET or not os.path.isfile(path):
        sys.exit(0)  # 対象外は完全に silent

    try:
        proc = subprocess.run(
            CMD + [path], capture_output=True, text=True, timeout=TIMEOUT
        )
        report = json.loads(proc.stdout)
    except Exception as e:
        emit(
            f"【DESIGN.md lint 未実行】{path}\n"
            f"lint を走らせられなかった（{type(e).__name__}）。ネット断か npx の失敗。\n"
            f"検証できていないので、`npx -y @google/design.md@latest lint {path}` を手で通すこと。"
        )
        return

    summary = report.get("summary") or {}
    errors, warnings = summary.get("errors", 0), summary.get("warnings", 0)
    if not errors and not warnings:
        sys.exit(0)  # clean なら黙る

    lines = [f"【DESIGN.md lint】{path} — errors {errors} / warnings {warnings}"]
    for f in report.get("findings", []):
        if f.get("severity") == "info":
            continue
        where = f.get("path") or "-"
        lines.append(f"  [{f.get('severity')}] {where}: {f.get('message')} ({f.get('rule')})")
    lines.append("**この編集で DESIGN.md を壊している。先にこれを直してから次に進むこと。**")
    emit("\n".join(lines))


def emit(text: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
