#!/bin/bash
# Usage: post_rereview.sh [<pr_number>] [<bots>] [<codex_focus>]
# bots: カンマ区切りの bot id（coderabbit,codex,copilot,gemini,cursor）。省略・all はそのリポで検出した bot すべて
#       （pr-review-wait/scripts/detect-bots.sh。頼み方の表は pr-review-wait/references/bots.md）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DETECT="$HERE/../../pr-review-wait/scripts/detect-bots.sh"

PR_NUMBER="${1:-}"
BOTS="${2:-all}"
CODEX_FOCUS="${3:-}"

if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(gh pr view --json number --jq '.number' 2>/dev/null || echo "")
  if [ -z "$PR_NUMBER" ]; then
    echo "ERROR: PR 番号を引数で指定するか、open PR があるブランチで実行してください" >&2
    exit 2
  fi
fi

REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

case "$BOTS" in
  all|both|"") BOTS=$(bash "$DETECT" "$REPO" | paste -sd, -) ;;
esac
if [ -z "$BOTS" ]; then
  echo "このリポにはレビュー bot が見つからない（detect-bots.sh が 0 件）。再レビューは投げない" >&2
  exit 3
fi

LINES=()
for b in $(printf '%s' "$BOTS" | tr ',' ' '); do
  case "$b" in
    coderabbit|coderabbitai) LINES+=("@coderabbitai review") ;;
    codex|chatgpt) LINES+=("@codex review${CODEX_FOCUS:+ $CODEX_FOCUS}") ;;
    gemini) LINES+=("/gemini review") ;;
    cursor|bugbot) LINES+=("bugbot run") ;;
    copilot)
      gh pr edit "$PR_NUMBER" -R "$REPO" --add-reviewer "@copilot" >/dev/null
      echo "Requested: Copilot（レビュアーとして再依頼）"
      ;;
    *) echo "ERROR: 不明な bot '$b'（coderabbit / codex / copilot / gemini / cursor）" >&2; exit 2 ;;
  esac
done

if [ "${#LINES[@]}" -gt 0 ]; then
  BODY=$(printf '%s\n\n' "${LINES[@]}")  # 末尾の空行は $() が落とす
  URL=$(gh api "repos/$REPO/issues/$PR_NUMBER/comments" -X POST -f body="$BODY" --jq '.html_url')
  echo "Posted: $URL"
  echo "Body:"
  echo "$BODY" | sed 's/^/  /'
fi
