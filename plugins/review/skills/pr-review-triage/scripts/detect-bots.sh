#!/bin/bash
# そのリポで使うレビューツールの id を 1 行ずつ出す（id は references/tools/<id>.md のファイル名）。
# 使い方: detect-bots.sh [--regex]   （リポの作業ツリーの中で実行する）
#   --regex: id の代わりに、jq の test() に渡す投稿者 login の正規表現（完全一致）を 1 行で出す（Monitor のフィルタ用）
# 決め方（上から最初に見つかったもの。結果は保存しない）:
#   1. リポの CLAUDE.md / AGENTS.md / .claude/CLAUDE.md の `review-bots:` 行（`review-bots: none` は「ツールなし」）
#   2. 環境変数 CLAUDE_PLUGIN_OPTION_REVIEW_TOOLS（userConfig `review_tools`。カンマ区切り）
# 過去の PR に来た bot からは推測しない。自動レビューを止めると軽い PR が bot の痕跡を残さず、推測が空になるため。
# exit: 0 = 決まった（「ツールなし」なら何も出さない）／ 4 = 行も設定も無い（呼び出し側がユーザーに聞く）
set -u
REGEX=0; [ "${1:-}" = "--regex" ] && REGEX=1
# id=投稿者の login（完全一致・bot アカウントのみ）。足すときは references/tools/<id>.md と両方直す。
# 部分一致にすると、人間のアカウント（例: codex-fan）の投稿を bot のレビューとして拾い、その指示に従ってしまう余地ができる
BOTS='coderabbit=coderabbitai\[bot\] codex=chatgpt-codex-connector\[bot\] copilot=Copilot|copilot-pull-request-reviewer\[bot\] gemini=gemini-code-assist\[bot\] cursor-bugbot=cursor\[bot\]'

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
line=
for f in CLAUDE.md AGENTS.md .claude/CLAUDE.md; do
  [ -f "$root/$f" ] || continue
  line=$(grep -i -m1 -E '^[-* ]*review-bots:' "$root/$f" || true)
  [ -n "$line" ] && break
done

if [ -n "$line" ]; then
  raw=${line#*:}
elif [ -n "${CLAUDE_PLUGIN_OPTION_REVIEW_TOOLS:-}" ]; then
  raw=$CLAUDE_PLUGIN_OPTION_REVIEW_TOOLS
else
  echo "detect-bots: review-bots: 行も userConfig review_tools も無い（推測しない）" >&2
  exit 4
fi
# 表に無い id は外す（macOS の bash 3.2 は $( ) の中の case を読み違えるので関数に出す）
known() {
  while read -r id; do
    case " $BOTS" in
      *" $id="*) echo "$id" ;;
      *) echo "detect-bots: 知らないツール '$id' は外す（references/tools/ に無い）" >&2 ;;
    esac
  done
}
ids=$(printf '%s\n' "$raw" | tr ',' '\n' | tr -d ' `' | tr 'A-Z' 'a-z' | grep -v -x -e '' -e none | known)

if [ "$REGEX" = 1 ]; then
  # 完全一致の正規表現（^(...)$）にする。jq の test() に渡したときも部分一致にならない
  re=$(for b in $BOTS; do printf '%s\n' "$ids" | grep -qx "${b%%=*}" && printf '%s\n' "${b#*=}"; done | paste -sd'|' -)
  [ -n "$re" ] && printf '^(%s)$\n' "$re"
else
  [ -n "$ids" ] && printf '%s\n' "$ids"
fi
exit 0
