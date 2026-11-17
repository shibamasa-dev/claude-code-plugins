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
# The review-* lines are read from the default branch (origin/<default>), so a PR cannot pick the tools that review it.
# base <name> <CLAUDE.md on the default branch, or empty> <CLAUDE.md on the branch> -> a clone on branch feat with an origin
base() { d="$T/$1"; w="$d/work"; mkdir -p "$w" || exit 1; g() { git -C "$w" -c user.name=t -c user.email=t@t "$@"; }
         b=${B:-main}; g init -q -b "$b"; printf '%s\n' "${2:-# no line}" > "$w/CLAUDE.md"; g add CLAUDE.md; g commit -qm base
         git init -q --bare -b "$b" "$d/origin.git" && g remote add origin "$d/origin.git" && g push -q origin "$b" && g fetch -q origin || exit 1
         g checkout -qb feat; printf '%s\n' "$3" > "$w/CLAUDE.md"; g commit -qam branch; echo "$w"; }
row 'branch edits review-heavy: the default branch line wins' "$(det "$(base edit 'review-heavy: coderabbit' 'review-heavy: none')")" 'coderabbit/0'
row 'line only on the branch: userConfig is used' "$(det "$(base new '' 'review-heavy: codex')" '' CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY=gemini)" 'gemini/0'
row 'line only on the branch, no setting: exit 4' "$(det "$(base new2 '' 'review-heavy: codex')")" '/4'
note=$(cd "$(repo noorigin 'review-heavy: codex')" && env -u CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY bash "$D" 2>&1 >/dev/null)
row 'no origin: a one-line note on stderr' "$(printf '%s' "$note" | grep -q 'no origin remote' && echo yes || echo no)" 'yes'
# trunk default, a non-default origin/main carrying the branch's line, no local origin/HEAD (as with git < 2.48)
w=$(B=trunk base trunk 'review-heavy: coderabbit' 'review-heavy: none')
git -C "$w" push -q origin feat:main && git -C "$w" fetch -q origin && git -C "$w" remote set-head origin -d 2>/dev/null
row 'default branch trunk (no local origin/HEAD): its line wins' "$(det "$w")" 'coderabbit/0'
w=$(base unreadable '' 'review-heavy: codex'); git -C "$w" remote set-url origin "$T/missing.git"; git -C "$w" update-ref -d refs/remotes/origin/main
row 'origin unreadable: the working tree line is not used' "$(det "$w")" '/4'
w=$(base single 'review-heavy: coderabbit' 'review-heavy: none'); git -C "$w" push -q origin feat; git clone -q --single-branch -b feat "$T/single/origin.git" "$T/single/clone"
row 'single-branch clone: the default branch line is fetched' "$(det "$T/single/clone")" 'coderabbit/0'
# origin unreachable and no origin/HEAD: exit 4, and a second run makes no network call (the failure is kept for an hour)
w=$(base netmiss 'review-heavy: coderabbit' 'review-heavy: none'); git -C "$w" remote set-head origin -d 2>/dev/null; git -C "$w" remote set-url origin ssh://nohost.invalid/x.git
row 'origin unreachable, no origin/HEAD: exit 4' "$(det "$w" '' "GIT_SSH_COMMAND=touch $T/net; false")" '/4'
rm -f "$T/net"; det "$w" '' "GIT_SSH_COMMAND=touch $T/net; false" >/dev/null
row 'origin unreachable: a second run makes no network call' "$([ -f "$T/net" ] && echo network || echo cached)" 'cached'
# trunk default, pushed non-default main with the branch's line, no origin/HEAD, origin unreachable: main is never used
w=$(B=trunk base unreach 'review-heavy: coderabbit' 'review-heavy: none')
git -C "$w" push -q origin feat:main && git -C "$w" fetch -q origin && git -C "$w" remote set-head origin -d 2>/dev/null; mv "$T/unreach/origin.git" "$T/unreach/moved.git"
row 'origin unreachable, pushed main: main is not used (exit 4)' "$(det "$w")" '/4'
git init -q "$T/gdother"
row 'GIT_DIR naming another repo: the default branch line wins' "$(det "$(base gitdir 'review-heavy: coderabbit' 'review-heavy: none')" '' "GIT_DIR=$T/gdother/.git")" 'coderabbit/0'
row 'non-ASCII path with a space: the default branch line wins' "$(det "$(base "日本語 dir/プロジェクト" 'review-heavy: coderabbit' 'review-heavy: none')")" 'coderabbit/0'
exit $fail
