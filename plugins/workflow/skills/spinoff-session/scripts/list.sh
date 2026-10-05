#!/usr/bin/env bash
# list.sh - 稼働中の spin_ tmux セッション一覧 / spin worktree 一覧 / claude agents を表示
set -euo pipefail

echo "=== 稼働中の spin_ セッション ==="
sessions_file=$(mktemp "${TMPDIR:-/tmp}/list-sessions.XXXXXX")
tmux list-sessions -F '#{session_name} #{session_created} #{session_activity}' 2>/dev/null \
  | grep -E '^spin_' > "$sessions_file" 2>/dev/null || true

if [ -s "$sessions_file" ]; then
  now=$(date +%s)
  while IFS=' ' read -r name created activity; do
    idle_sec=$(( now - activity ))
    idle_min=$(( idle_sec / 60 ))
    created_fmt=$(date -r "$created" "+%Y-%m-%d %H:%M:%S" 2>/dev/null \
      || date -d "@$created" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "unknown")
    printf "  %-40s  created: %s  idle: %d min\n" "$name" "$created_fmt" "$idle_min"
  done < "$sessions_file"
else
  echo "  (稼働中の spin_ セッションなし)"
fi
rm -f "$sessions_file"

echo ""
echo "=== spin worktrees ==="
wt_root="${SPINOFF_WORKTREE_ROOT:-$HOME/.worktrees}"
wt_found=0
if [ -d "$wt_root" ]; then
  for wt in "$wt_root"/*/; do
    [ -d "$wt" ] || continue
    wt="${wt%/}"
    git -C "$wt" rev-parse --git-dir >/dev/null 2>&1 || continue
    branch=$(git -C "$wt" symbolic-ref --short -q HEAD 2>/dev/null) || continue
    case "$branch" in
      spin/*) ;;
      *) continue ;;
    esac
    wt_found=1
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      clean_label="dirty"
    else
      clean_label="clean"
    fi
    if git -C "$wt" merge-base --is-ancestor "$branch" main >/dev/null 2>&1; then
      merged_label="merged"
    else
      merged_label="unmerged"
    fi
    printf "  %-50s  %-20s  %s / %s\n" "$wt" "$branch" "$clean_label" "$merged_label"
  done
fi
if [ "$wt_found" -eq 0 ]; then
  echo "  (なし)"
fi

echo ""
echo "=== claude agents ==="
if command -v claude &>/dev/null; then
  claude agents --json 2>/dev/null || echo "  (claude agents 取得失敗)"
else
  echo "  (claude コマンドが見つかりません)"
fi
