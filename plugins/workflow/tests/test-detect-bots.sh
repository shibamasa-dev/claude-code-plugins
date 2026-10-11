#!/bin/bash
# Regression for pr-review-triage's detect-bots.sh. Checks, inside temporary git repos, the three ways the heavy tools are
# decided (a review-heavy: line, userConfig, neither) and `review-heavy: none`, plus reading and defaults for light
# (`review-light:`) and automatic review (`review-auto:`) (no gh, no network).
# Background: it used to guess from the bots on recent PRs, but with automatic review turned off, light PRs leave no trace,
#       the guess comes out empty, and some PRs get no review at all. Guessing was dropped; with no line and no setting it exits 4 so the caller asks.
set -u
D="$(cd "$(dirname "$0")/.." && pwd)/skills/pr-review-triage/scripts/detect-bots.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/detect-bots-test.XXXX")
trap 'rm -rf "$T"' EXIT

# repo <name> [CLAUDE.md content] -> path of the temporary repo
repo() { mkdir -p "$T/$1" && git -C "$T/$1" init -q && { [ -z "${2:-}" ] || printf '%s\n' "$2" > "$T/$1/CLAUDE.md"; }; echo "$T/$1"; }
# det <repo> [flag] [VAR=value ...] -> "output (comma-separated)/exit". Runs with the local userConfig values unset
det() { r=$1; flag=${2:-}; shift; [ $# -gt 0 ] && shift
        (cd "$r" && env -u CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY -u CLAUDE_PLUGIN_OPTION_REVIEW_LIGHT -u CLAUDE_PLUGIN_OPTION_REVIEW_AUTO "$@" \
           bash "$D" $flag 2>/dev/null | paste -sd, -; exit "${PIPESTATUS[0]}"); echo "/$?"; }
fail=0
row() { got=$(printf '%s' "$2" | tr -d '\n'); if [ "$got" = "$3" ]; then r=ok; else r=ng; fail=1; fi
        printf '  %-48s -> %s (expect ok)  [got %s / want %s]\n' "$1" "$r" "$got" "$3"; }

row 'prints the ids from the review-heavy: line' "$(det "$(repo line '- review-heavy: CodeRabbit, `codex`')")" 'coderabbit,codex/0'
row 'no line: uses userConfig review_heavy' "$(det "$(repo cfg '# no line')" '' CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY=gemini,copilot)" 'gemini,copilot/0'
row 'no line and no setting: prints nothing, exit 4' "$(det "$(repo nothing)")" '/4'
row 'review-heavy: none means "no tools", exit 0' "$(det "$(repo none 'review-heavy: none')")" '/0'
row 'no known id: not treated as none, exit 5' "$(det "$(repo typo 'review-heavy: coderabit')")" '/5'
row 'no review-light: line: claude' "$(det "$(repo light0 'review-heavy: codex')" --light)" 'claude/0'
row 'review-light: with tools prints those ids' "$(det "$(repo light1 'review-light: coderabbit, codex')" --light)" 'coderabbit,codex/0'
row 'review-light: claude plus a tool prints both' "$(det "$(repo light2 'review-light: claude, codex')" --light)" 'claude,codex/0'
row 'no review-auto: line: off' "$(det "$(repo auto0 'review-heavy: codex')" --auto)" 'off/0'
row 'reads review-auto: on' "$(det "$(repo auto1 '- review-auto: ON')" --auto)" 'on/0'
row 'review-auto: other than on / off: exit 5' "$(det "$(repo auto2 'review-auto: yes')" --auto)" '/5'
exit $fail
