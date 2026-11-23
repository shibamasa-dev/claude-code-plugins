#!/bin/bash
# Regression for dev-process/agent-review.sh: a reviewer that exits non-zero is reported as a failed review, not a result (#106).
# Background: the script judged success by whether each output file existed. CodeRabbit's file holds its stdout and stderr,
#       so an authentication error left a file with the error text and the failed run was printed as a finished review.
# codex and coderabbit are stubs on PATH (no service is called). The error texts are synthetic, not captured from a real run.
set -u
# A caller's repo-selecting git variables (a git hook sets GIT_DIR) must not point the fixtures at the caller's repo
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
S="$(cd "$(dirname "$0")/.." && pwd)/commands/dev-process/agent-review.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/agent-review-test.XXXX")
trap 'rm -rf "$T"' EXIT

# Stubs: codex prints CODEX_ERR on stderr and writes CODEX_TEXT to the --output-last-message file (nothing when unset),
# coderabbit prints CR_TEXT; both exit with *_RC
mkdir -p "$T/bin"
cat > "$T/bin/codex" <<'SH'
#!/bin/bash
out=""; while [ $# -gt 0 ]; do [ "$1" = --output-last-message ] && out=$2; shift; done
[ -n "${CODEX_ERR:-}" ] && printf '%s\n' "$CODEX_ERR" >&2
[ -n "${CODEX_TEXT+x}" ] && printf '%s\n' "$CODEX_TEXT" > "$out"
exit "${CODEX_RC:-0}"
SH
cat > "$T/bin/coderabbit" <<'SH'
#!/bin/bash
printf '%s\n' "${CR_TEXT:-}"
exit "${CR_RC:-0}"
SH
chmod +x "$T/bin/codex" "$T/bin/coderabbit"

# run <name> [VAR=value ...] -> runs the script in a fresh repo; stdout in $T/<name>.out, exit status in $T/<name>.rc
run() { n=$1; shift; mkdir -p "$T/$n" && git -C "$T/$n" init -q || exit 1
        (cd "$T/$n" && env -u CODEX_TEXT -u CODEX_RC -u CODEX_ERR -u CR_TEXT -u CR_RC PATH="$T/bin:$PATH" "$@" bash "$S" >"$T/$n.out" 2>/dev/null)
        echo $? > "$T/$n.rc"; }
fail=0
row() { if [ "$2" = ok ]; then r=ok; else r=ng; fail=1; fi; printf '  %-60s -> %s (expect ok)  [%s]\n' "$1" "$r" "$2"; }
# has <name> <text>: the output has a line equal to text
has() { grep -qxF -- "$2" "$T/$1.out"; }
# under <name> <heading> <text>: text appears after heading and before the next ━ rule that follows heading's own rule
under() { awk -v h="$2" -v t="$3" '$0 == h {s=1; next} s == 1 && /^━/ {s=2; next} s == 2 && /^━/ {exit} s == 2 && index($0, t) {f=1} END {exit !f}' "$T/$1.out"; }

RULE='━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
CODEX_OK='[P2] codex finding: null check missing in parse()'
CR_OK='coderabbit finding: rename tmp to something descriptive'
CR_ERR='Error: authentication required. Run `coderabbit auth login`.'
CODEX_ERR='Error: not logged in. Run `codex login`.'

# 1. Both succeed: stdout is exactly the format the script printed before this change, exit 0
run ok CODEX_TEXT="$CODEX_OK" CR_TEXT="$CR_OK"
printf '%s\n' '✅ All reviews are done!' '' "$RULE" '📋 Codex Review' "$RULE" "$CODEX_OK" '' "$RULE" '🐰 CodeRabbit Review' "$RULE" "$CR_OK" > "$T/ok.want"
v=ok; cmp -s "$T/ok.out" "$T/ok.want" || v="stdout differs"; [ "$(cat "$T/ok.rc")" = 0 ] || v="exit $(cat "$T/ok.rc")"
row 'both succeed: output unchanged, exit 0' "$v"

# 2. CodeRabbit exits 1 with an error text in its output file
run crfail CODEX_TEXT="$CODEX_OK" CR_TEXT="$CR_ERR" CR_RC=1
v=ok
has crfail '❌ CodeRabbit review FAILED (exit 1)' || v="no FAILED line"
under crfail '🐰 CodeRabbit Review' "$CR_ERR" && v="error text shown as the CodeRabbit review"
under crfail '❌ CodeRabbit review FAILED (exit 1)' "$CR_ERR" || v="error text not shown under the FAILED line"
under crfail '📋 Codex Review' "$CODEX_OK" || v="Codex findings not printed"
has crfail '✅ All reviews are done!' && v="still says all reviews are done"
[ "$(cat "$T/crfail.rc")" != 0 ] || v="exit 0"
row 'CodeRabbit exits 1 with error text: reported as failed' "$v"

# 3. Codex exits 1 with an error on stderr and writes no output file
run cxfail CODEX_RC=1 CODEX_ERR="$CODEX_ERR" CR_TEXT="$CR_OK"
v=ok
has cxfail '❌ Codex review FAILED (exit 1)' || v="no FAILED line"
under cxfail '❌ Codex review FAILED (exit 1)' "$CODEX_ERR" || v="error text not shown under the FAILED line"
under cxfail '🐰 CodeRabbit Review' "$CR_OK" || v="CodeRabbit findings not printed"
has cxfail '✅ All reviews are done!' && v="still says all reviews are done"
[ "$(cat "$T/cxfail.rc")" != 0 ] || v="exit 0"
row 'Codex exits 1 with an error on stderr: reported as failed' "$v"

# 4. Codex exits 0 but writes no output file: failed on the missing file alone
run cxnofile CR_TEXT="$CR_OK"
v=ok
has cxnofile '❌ Codex review FAILED (no output file)' || v="no FAILED line"
under cxnofile '🐰 CodeRabbit Review' "$CR_OK" || v="CodeRabbit findings not printed"
[ "$(cat "$T/cxnofile.rc")" != 0 ] || v="exit 0"
row 'Codex exits 0 with no output file: reported as failed' "$v"
exit $fail
