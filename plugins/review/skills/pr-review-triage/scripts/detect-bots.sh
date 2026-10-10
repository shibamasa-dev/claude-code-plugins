#!/bin/bash
# そのリポのレビューの設定（heavy・light に使うツール、ツールの自動レビューが ON か）を出す。
# 使い方: detect-bots.sh [--light | --auto] [--regex]   （リポの作業ツリーの中で実行する）
#   （引数なし）: heavy の PR に使うツールの id を 1 行ずつ（id は references/tools/<id>.md のファイル名）
#   --light: light の PR に使うもの。`claude`（Claude がレビュー。既定）か、ツールの id を 1 行ずつ
#   --auto:  ツールの自動レビューが ON か。`on` / `off`（既定 off）
#   --regex: id の代わりに、jq の test() に渡す投稿者 login の正規表現（完全一致）を 1 行で出す（Monitor のフィルタ用）
# 決め方（上から最初に見つかったもの。結果は保存しない）:
#   1. リポの CLAUDE.md / AGENTS.md / .claude/CLAUDE.md の行（`review-heavy:` / `review-light:` / `review-auto:`。`review-heavy: none` は「ツールなし」）
#   2. 環境変数 CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY / _LIGHT / _AUTO（userConfig `review_heavy` / `review_light` / `review_auto`）
#   3. 既定: light は `claude`、auto は `off`。heavy には既定が無い（exit 4）
# 過去の PR に来た bot からは推測しない。自動レビューを止めると軽い PR が bot の痕跡を残さず、推測が空になるため。
# exit: 0 = 決まった（「ツールなし」なら何も出さない）／ 4 = heavy の行も設定も無い ／ 5 = 書いてあるが読めない
#       （知っている id が 1 つも無い、auto が on / off 以外、light で claude とツールの id を並べた）（4・5 は呼び出し側がユーザーに聞く）
set -u
KEY=heavy; REGEX=0
for a in "$@"; do
  case "$a" in
    --light) KEY=light ;;
    --auto) KEY=auto ;;
    --regex) REGEX=1 ;;
  esac
done
# id=投稿者の login（完全一致・bot アカウントのみ）。足すときは references/tools/<id>.md と両方直す。
# 部分一致にすると、人間のアカウント（例: codex-fan）の投稿を bot のレビューとして拾い、その指示に従ってしまう余地ができる
BOTS='coderabbit=coderabbitai\[bot\] codex=chatgpt-codex-connector\[bot\] copilot=Copilot|copilot-pull-request-reviewer\[bot\] gemini=gemini-code-assist\[bot\] cursor-bugbot=cursor\[bot\]'

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
line=
for f in CLAUDE.md AGENTS.md .claude/CLAUDE.md; do
  [ -f "$root/$f" ] || continue
  line=$(grep -i -m1 -E "^[-* ]*review-$KEY:" "$root/$f" || true)
  [ -n "$line" ] && break
done

case $KEY in
  heavy) env=${CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY:-} ;;
  light) env=${CLAUDE_PLUGIN_OPTION_REVIEW_LIGHT:-} ;;
  auto) env=${CLAUDE_PLUGIN_OPTION_REVIEW_AUTO:-} ;;
esac
if [ -n "$line" ]; then
  raw=${line#*:}
elif [ -n "$env" ]; then
  raw=$env
elif [ "$KEY" = light ]; then
  raw=claude
elif [ "$KEY" = auto ]; then
  raw=off
else
  echo "detect-bots: review-heavy: 行も userConfig review_heavy も無い（推測しない）" >&2
  exit 4
fi
norm=$(printf '%s\n' "$raw" | tr ',' '\n' | tr -d ' `' | tr 'A-Z' 'a-z' | grep -v -x '')

if [ "$KEY" = auto ]; then
  case "$norm" in
    on|off) echo "$norm"; exit 0 ;;
    *) echo "detect-bots: review-auto は on か off（'$(printf '%s' "$norm" | paste -sd, -)' は読めない）" >&2; exit 5 ;;
  esac
fi
# light の `claude` はツールではない（Claude がレビューする）。--regex では待つツールが無いので何も出さない
if [ "$KEY" = light ] && [ "$norm" = claude ]; then
  [ "$REGEX" = 1 ] || echo claude
  exit 0
fi
# claude とツールの混在は、どちらの手順で回すか決まらない。黙って claude を落としてツールだけにしない
if [ "$KEY" = light ] && printf '%s\n' "$norm" | grep -qx claude; then
  echo "detect-bots: review-light の claude はほかの id と並べられない（'$(printf '%s' "$norm" | paste -sd, -)'。claude だけか、ツールの id だけにする）" >&2
  exit 5
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
asked=$(printf '%s\n' "$norm" | grep -v -x none)
ids=$(printf '%s\n' "$asked" | grep -v -x '' | known)
# none 以外を書いたのに知っている id が 1 つも残らない（綴り違いなど）を「ツールなし」と同じ exit 0 にしない
if [ -n "$asked" ] && [ -z "$ids" ]; then
  echo "detect-bots: 知っている id が 1 つも無い（ツールなしにするなら review-$KEY: none と書く）" >&2
  exit 5
fi

if [ "$REGEX" = 1 ]; then
  # 完全一致の正規表現（^(...)$）にする。jq の test() に渡したときも部分一致にならない
  re=$(for b in $BOTS; do printf '%s\n' "$ids" | grep -qx "${b%%=*}" && printf '%s\n' "${b#*=}"; done | paste -sd'|' -)
  [ -n "$re" ] && printf '^(%s)$\n' "$re"
else
  [ -n "$ids" ] && printf '%s\n' "$ids"
fi
exit 0
