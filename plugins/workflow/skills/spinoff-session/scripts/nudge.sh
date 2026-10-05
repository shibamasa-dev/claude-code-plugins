#!/usr/bin/env bash
# nudge.sh - 稼働中の spin_ セッションに指示を1行送る（起動元がレビュー到着などを知らせるのに使う）
# Usage: nudge.sh <session> "<message>"
set -euo pipefail

session="${1:?Usage: nudge.sh <session> \"<message>\"}"
message="${2:?Usage: nudge.sh <session> \"<message>\"}"

case "$session" in
  spin_*) ;;
  *) echo "ERROR: spin_ 接頭辞のセッションにだけ送れます: $session" >&2; exit 1 ;;
esac
if ! tmux has-session -t "$session" 2>/dev/null; then
  echo "ERROR: セッションがありません: $session" >&2
  exit 1
fi

# -l で文字どおり送り、Enter は別に送る（メッセージ中のキー名を解釈させない）
tmux send-keys -t "$session" -l "$message"
tmux send-keys -t "$session" Enter
echo "送信しました: $session"
