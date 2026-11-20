#!/bin/bash
# Where full-test-gate keeps its records: ${CLAUDE_PLUGIN_DATA}/full-test, copied once from the old
# ~/.claude/state/full-test, and the `run` command the hook prints carries the directory into Bash.
# HOME and CLAUDE_PLUGIN_DATA point at a temp directory, so the real ~/.claude is untouched.
set -u
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES FULL_TEST_STATE_DIR
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/full-test-gate.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/ftg-state.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
g() { git -C "$1" -c user.name=t -c user.email=t@t "${@:2}"; }
w="$T/work"; mkdir -p "$w/src" "$w/.claude"
g "$w" init -q -b main; echo a > "$w/src/a"; echo '{"command": "true", "paths": ["src"]}' > "$w/.claude/full-test.json"
g "$w" add .; g "$w" commit -qm base
git init -q --bare -b main "$T/origin.git"; g "$w" remote add origin "$T/origin.git"; g "$w" push -q origin main; g "$w" fetch -q origin
g "$w" remote set-head origin main
row() { printf '  %-62s -> %-5s (expect %s)\n' "$1" "$2" "$3"; }
yes_no() { [ "$1" ] && echo yes || echo no; }
status() { out=$(cd "$w" && HOME="$1" CLAUDE_PLUGIN_DATA="$2" python3 "$H" status 2>&1); rc=$?
  if [ $rc = 0 ] && grep -q '^Since the last full test run' <<<"$out"; then echo recorded
  elif [ $rc = 0 ] && grep -q 'No full test run recorded' <<<"$out"; then echo none; else echo "error$rc"; fi; }

# The old record, written by the hook itself at the old place
H1="$T/h1"; mkdir -p "$H1"
(cd "$w" && HOME="$H1" FULL_TEST_STATE_DIR="$H1/.claude/state/full-test" python3 "$H" run >/dev/null 2>&1)
row 'old record, new missing: status reads it from ${CLAUDE_PLUGIN_DATA}' "$(status "$H1" "$T/h1/data/testing-test")" recorded
row '  ...copied there' "$(yes_no "$(ls "$T/h1/data/testing-test/full-test/"*.json 2>/dev/null)")" yes
row '  ...and the old record stays as the backup' "$(yes_no "$(ls "$H1/.claude/state/full-test/"*.json 2>/dev/null)")" yes

H2="$T/h2"; mkdir -p "$H2" "$T/h2/data/testing-test/full-test"
(cd "$w" && HOME="$H2" FULL_TEST_STATE_DIR="$H2/.claude/state/full-test" python3 "$H" run >/dev/null 2>&1)
row 'new directory already there: the old record is not copied' "$(status "$H2" "$T/h2/data/testing-test")" none

H3="$T/h3"; mkdir -p "$H3"; D3="$T/h3/data/testing-test"
msg=$(printf '{"hook_event_name":"SessionStart","cwd":"%s"}' "$w" | HOME="$H3" CLAUDE_PLUGIN_DATA="$D3" python3 "$H" 2>/dev/null)
cmd=$(grep -o 'CLAUDE_PLUGIN_DATA=[^`]* run' <<<"$msg" | head -1)
(cd "$w" && HOME="$H3" bash -c "$cmd" >/dev/null 2>&1)
row '`run` as the hook prints it records where the hook reads' "$(status "$H3" "$D3")" recorded
