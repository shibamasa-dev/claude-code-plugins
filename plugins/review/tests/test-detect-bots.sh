#!/bin/bash
# pr-review-triage の detect-bots.sh の回帰。heavy のツールの決め方の 3 経路（review-heavy: 行・userConfig・どちらも無し）と
# `review-heavy: none`、light（`review-light:`）と自動レビュー（`review-auto:`）の読み取りと既定を、
# 一時的な git リポの中で確かめる（gh もネットワークも使わない）。
# 背景: 以前は直近の PR に来た bot から推測していたが、自動レビューを止めると軽い PR が痕跡を残さず、
#       推測が空になって誰もレビューしない PR が出る。推測はやめ、行も設定も無ければ exit 4 で呼び出し側に聞かせる。
set -u
D="$(cd "$(dirname "$0")/.." && pwd)/skills/pr-review-triage/scripts/detect-bots.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/detect-bots-test.XXXX")
trap 'rm -rf "$T"' EXIT

# repo <名前> [CLAUDE.md の中身] → 一時リポのパス
repo() { mkdir -p "$T/$1" && git -C "$T/$1" init -q && { [ -z "${2:-}" ] || printf '%s\n' "$2" > "$T/$1/CLAUDE.md"; }; echo "$T/$1"; }
# det <リポ> [フラグ] [環境変数=値 ...] → 「出力（カンマ区切り）/exit」。手元の userConfig の値は外して回す
det() { r=$1; flag=${2:-}; shift; [ $# -gt 0 ] && shift
        (cd "$r" && env -u CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY -u CLAUDE_PLUGIN_OPTION_REVIEW_LIGHT -u CLAUDE_PLUGIN_OPTION_REVIEW_AUTO "$@" \
           bash "$D" $flag 2>/dev/null | paste -sd, -; exit "${PIPESTATUS[0]}"); echo "/$?"; }
fail=0
row() { got=$(printf '%s' "$2" | tr -d '\n'); if [ "$got" = "$3" ]; then r=ok; else r=ng; fail=1; fi
        printf '  %-48s -> %s (ok 期待)  [実測 %s / 期待 %s]\n' "$1" "$r" "$got" "$3"; }

row 'review-heavy: 行の id を出す' "$(det "$(repo line '- review-heavy: CodeRabbit, `codex`')")" 'coderabbit,codex/0'
row '行が無ければ userConfig review_heavy を使う' "$(det "$(repo cfg '# no line')" '' CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY=gemini,copilot)" 'gemini,copilot/0'
row '行も設定も無ければ何も出さず exit 4' "$(det "$(repo nothing)")" '/4'
row 'review-heavy: none は「ツールなし」で exit 0' "$(det "$(repo none 'review-heavy: none')")" '/0'
row '知っている id が 1 つも無ければ none 扱いせず exit 5' "$(det "$(repo typo 'review-heavy: coderabit')")" '/5'
row 'review-light: 行が無ければ claude' "$(det "$(repo light0 'review-heavy: codex')" --light)" 'claude/0'
row 'review-light: にツールを書けばその id を出す' "$(det "$(repo light1 'review-light: coderabbit, codex')" --light)" 'coderabbit,codex/0'
row 'review-auto: 行が無ければ off' "$(det "$(repo auto0 'review-heavy: codex')" --auto)" 'off/0'
row 'review-auto: on を読む' "$(det "$(repo auto1 '- review-auto: ON')" --auto)" 'on/0'
row 'review-auto: が on / off 以外なら exit 5' "$(det "$(repo auto2 'review-auto: yes')" --auto)" '/5'
exit $fail
