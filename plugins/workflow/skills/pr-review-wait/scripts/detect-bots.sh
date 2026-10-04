#!/bin/bash
# そのリポでレビューしている bot の id を 1 行ずつ出す（references/bots.md の表の id）。
# 使い方: detect-bots.sh [--regex] [owner/repo]   （省略時はカレントのリポ）
#   --regex: id の代わりに、jq の test() に渡す投稿者 login の正規表現（完全一致）を 1 行で出す（Monitor のフィルタ用）
# 優先順: リポの CLAUDE.md / AGENTS.md の `review-bots:` 行 → 直近の PR の実績。結果は保存しない。
set -u
REGEX=0; [ "${1:-}" = "--regex" ] && { REGEX=1; shift; }
REPO="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)}"
[ -n "$REPO" ] || { echo "detect-bots: リポを特定できない" >&2; exit 2; }
# 投稿者は GitHub App の bot アカウント（user.type == "Bot"）の login と完全一致で見る。部分一致にすると、
# 人間のアカウント（例: codex-fan）の投稿を bot のレビューとして拾い、その指示に従ってしまう余地ができる
BOTS='coderabbit=coderabbitai\[bot\] codex=chatgpt-codex-connector\[bot\] copilot=Copilot|copilot-pull-request-reviewer\[bot\] gemini=gemini-code-assist\[bot\] cursor=cursor\[bot\]'

# 1. 明示の指定（作業ツリーにあればそれを、無ければ GitHub の既定ブランチから読む）
for f in CLAUDE.md AGENTS.md .claude/CLAUDE.md; do
  body=$( { [ -f "$f" ] && [ "$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" = "$REPO" ] && cat "$f"; } \
          || gh api "repos/$REPO/contents/$f" --jq .content 2>/dev/null | base64 -d 2>/dev/null )
  line=$(printf '%s\n' "$body" | grep -i -m1 -E '^[-* ]*review-bots:' || true)
  if [ -n "$line" ]; then
    ids=$(printf '%s\n' "${line#*:}" | tr ',' '\n' | tr -d ' `' | tr 'A-Z' 'a-z' | grep -v -x -e '' -e none)
    break
  fi
done

# 2. 指定が無ければ、直近の PR に実際に来た bot
if [ -z "${line:-}" ]; then
logins=$(gh pr list -R "$REPO" --state all --limit "${DETECT_BOTS_PRS:-5}" --json number --jq '.[].number' 2>/dev/null \
  | while read -r n; do
      gh api "repos/$REPO/pulls/$n/reviews" --jq '.[] | select(.user.type == "Bot") | .user.login' 2>/dev/null
      gh api "repos/$REPO/pulls/$n/comments" --jq '.[] | select(.user.type == "Bot") | .user.login' 2>/dev/null
      # 「上限に達したので動けなかった」等の通知は、bot が入っていてもレビューしていない印なので数えない
      gh api "repos/$REPO/issues/$n/comments" --jq '.[] | select(.user.type == "Bot") | select(.body | test("usage limit|couldn.t run"; "i") | not) | .user.login' 2>/dev/null
      gh api "repos/$REPO/issues/$n/reactions" --jq '.[] | select(.user.type == "Bot") | .user.login' 2>/dev/null
    done | sort -u)
ids=$(for b in $BOTS; do
  id=${b%%=*}; pat=${b#*=}
  printf '%s\n' "$logins" | grep -q -x -E "$pat" && echo "$id"
done)
fi

if [ "$REGEX" = 1 ]; then
  # 完全一致の正規表現（^(...)$）にする。jq の test() に渡したときも部分一致にならない
  re=$(for b in $BOTS; do printf '%s\n' "$ids" | grep -qx "${b%%=*}" && printf '%s\n' "${b#*=}"; done | paste -sd'|' -)
  [ -n "$re" ] && printf '^(%s)$\n' "$re"
else
  [ -n "$ids" ] && printf '%s\n' "$ids"
fi
exit 0
