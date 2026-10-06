#!/bin/bash
# pr-review-wait の detect-bots.sh の回帰。gh を差し替えて、直近の PR に来た投稿だけを与える。
# 背景: 利用上限のコメントを数えずに捨てていたため、上限の回しか来ていない Codex が待つ対象から漏れ、
#       「未レビュー」の扱いに届かなかった（PR #13 の Codex 指摘）。
set -u
D="$(cd "$(dirname "$0")/.." && pwd)/skills/pr-review-wait/scripts/detect-bots.sh"
T=$(mktemp -d /tmp/detect-bots-test.XXXX)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/cwd"
# 偽の gh: pr list は PR #7 だけ、issues/7/comments は $ISSUE_COMMENTS、他の一覧は空、contents は無し
cat > "$T/bin/gh" <<'GH'
#!/bin/bash
jqx=; prev=
for a in "$@"; do [ "$prev" = --jq ] && jqx=$a; prev=$a; done
case "$1 $2" in
  "pr list") echo '[{"number":7}]' | jq -r "$jqx" ;;
  "api repos/o/r/issues/7/comments") printf '%s' "$ISSUE_COMMENTS" | jq -r "$jqx" ;;
  "api repos/o/r/contents/"*) exit 1 ;;
  "api "*) echo '[]' | jq -r "$jqx" ;;
  *) exit 1 ;;
esac
GH
chmod +x "$T/bin/gh"
det() { (cd "$T/cwd" && ISSUE_COMMENTS=$1 PATH="$T/bin:$PATH" bash "$D" o/r | paste -sd, -); }
row() { printf '  %-52s -> %-8s (%s 期待)\n' "$1" "${2:-none}" "$3"; }

limit='[{"user":{"type":"Bot","login":"chatgpt-codex-connector[bot]"},"body":"You have reached your Codex usage limits for code reviews."}]'
human='[{"user":{"type":"User","login":"chatgpt-codex-connector[bot]"},"body":"usage limit"}]'
row 'Codex の上限コメントだけでも codex を待つ対象に入れる' "$(det "$limit")" codex
row '人間のアカウントの投稿は bot に数えない' "$(det "$human")" none
