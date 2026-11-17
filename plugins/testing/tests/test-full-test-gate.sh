#!/bin/bash
# full-test-gate reads .claude/full-test.json from the default branch (origin/<default>), so a branch cannot change the
# command that records a pass or drop the gate that blocks its own release. Without an origin remote it reads the working
# tree and says so on stderr. `run --working-tree` tries the working tree's config and never records.
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/full-test-gate.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/ftg-test.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
export FULL_TEST_STATE_DIR="$T/state"
BASE_CFG='{"command": "echo base > ran", "paths": ["src"], "gate": ["build-release"]}'
g() { git -C "$1" -c user.name=t -c user.email=t@t "${@:2}"; }
# repo <name> <config on the default branch, or empty> [origin|none] -> path of a clone on branch feat
repo() {
  d="$T/$1"; w="$d/work"; mkdir -p "$w/src" "$w/.claude" || exit 1
  g "$w" init -q -b main && echo a > "$w/src/a"
  [ -n "$2" ] && printf '%s\n' "$2" > "$w/.claude/full-test.json"
  g "$w" add src .claude 2>/dev/null; g "$w" commit -qm base
  if [ "${3:-origin}" = origin ]; then
    git init -q --bare -b main "$d/origin.git" && g "$w" remote add origin "$d/origin.git" \
      && g "$w" push -q origin main && g "$w" fetch -q origin || exit 1
  fi
  g "$w" checkout -qb feat; echo "$w"
}
branch_cfg() { printf '%s\n' "$2" > "$1/.claude/full-test.json"; g "$1" add .claude; g "$1" commit -qm cfg; }
ran() { cat "$1/ran" 2>/dev/null || echo none; }
recorded() { ls "$FULL_TEST_STATE_DIR" 2>/dev/null | grep -q . && echo recorded || echo norecord; }
pre() { printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","cwd":"%s","tool_input":{"command":"./build-release.sh"}}' "$1" \
        | python3 "$H" | grep -q '"deny"' && echo deny || echo silent; }
fail=0
row() { printf '  %-60s -> %s (expect %s)\n' "$1" "$2" "$3"; [ "$2" = "$3" ] || fail=1; }

w=$(repo changed "$BASE_CFG"); branch_cfg "$w" '{"command": "echo branch > ran", "paths": ["src"], "gate": []}'
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'branch changed command: run uses the default branch command' "$(ran "$w")" base
echo b >> "$w/src/a"   # an unverified change in the target paths
row 'branch dropped the gate: release is still gated'           "$(pre "$w")" deny
g "$w" checkout -q -- src

rm -rf "$FULL_TEST_STATE_DIR"; rm -f "$w/ran"; (cd "$w" && python3 "$H" run --working-tree >/dev/null 2>&1)
row 'run --working-tree runs the working tree command'           "$(ran "$w")" branch
row 'run --working-tree never records'                           "$(recorded)" norecord

w=$(repo absent ''); branch_cfg "$w" "$BASE_CFG"
row 'config only on the branch: not opted in (status)'           "$(cd "$w" && python3 "$H" status | grep -q 'Not configured' && echo off || echo on)" off
row 'config only on the branch: release not gated'               "$(pre "$w")" silent

w=$(repo noorigin '{"command": "echo base > ran", "paths": ["src"], "base": "main"}' none); rm -rf "$FULL_TEST_STATE_DIR"
err=$(cd "$w" && python3 "$H" run 2>&1 >/dev/null)
row 'no origin: the working tree config is run'                  "$(ran "$w")" base
row 'no origin: a one-line note on stderr'                       "$(printf '%s' "$err" | grep -q 'no origin remote' && echo note || echo quiet)" note
exit $fail
