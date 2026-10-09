#!/bin/bash
# pr-review-triage の detect-bots.sh の回帰。使うツールの決め方の 3 経路（review-bots: 行・userConfig・どちらも無し）と、
# `review-bots: none` を、一時的な git リポの中で確かめる（gh もネットワークも使わない）。
# 背景: 以前は直近の PR に来た bot から推測していたが、自動レビューを止めると軽い PR が痕跡を残さず、
#       推測が空になって誰もレビューしない PR が出る。推測はやめ、行も設定も無ければ exit 4 で呼び出し側に聞かせる。
set -u
D="$(cd "$(dirname "$0")/.." && pwd)/skills/pr-review-triage/scripts/detect-bots.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/detect-bots-test.XXXX")
trap 'rm -rf "$T"' EXIT

# repo <名前> [CLAUDE.md の中身] → 一時リポのパス
repo() { mkdir -p "$T/$1" && git -C "$T/$1" init -q && { [ -z "${2:-}" ] || printf '%s\n' "$2" > "$T/$1/CLAUDE.md"; }; echo "$T/$1"; }
# det <リポ> [REVIEW_TOOLS の値] → 「出力（カンマ区切り）/exit」。期待と一致すれば ok
det() { (cd "$1" && CLAUDE_PLUGIN_OPTION_REVIEW_TOOLS=${2:-} bash "$D" 2>/dev/null | paste -sd, -; exit "${PIPESTATUS[0]}"); echo "/$?"; }
row() { got=$(printf '%s' "$2" | tr -d '\n'); [ "$got" = "$3" ] && r=ok || r=ng
        printf '  %-48s -> %s (ok 期待)  [実測 %s / 期待 %s]\n' "$1" "$r" "$got" "$3"; }

row 'review-bots: 行の id を出す' "$(det "$(repo line '- review-bots: CodeRabbit, `codex`')")" 'coderabbit,codex/0'
row '行が無ければ userConfig review_tools を使う' "$(det "$(repo cfg '# no line')" 'gemini,copilot')" 'gemini,copilot/0'
row '行も設定も無ければ何も出さず exit 4' "$(det "$(repo nothing)")" '/4'
row 'review-bots: none は「ツールなし」で exit 0' "$(det "$(repo none 'review-bots: none')")" '/0'
