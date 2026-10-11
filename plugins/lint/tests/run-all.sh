#!/bin/bash
# Regression sweep for this plugin's hooks (runs every tests/test-*.sh and tallies the results).
#
# Usage: bash tests/run-all.sh
# Only rows that do not match the expectation get a ❌. Even if the totals look right, stop and read if there is a single ❌.
cd "$(dirname "$0")" || exit 1
for s in test-*.sh; do
  echo; echo "▼ $s"
  bash "$s" 2>&1
  # Do not let a script that crashed midway hide behind "0 mismatches" (awk does not see the pipe's exit code, so turn it into a row and count it)
  rc=$?; [ "$rc" = 0 ] && r=ok || r=crashed
  # Width specifiers (%-56s) can cut a multibyte character in half in some locales, which awk then cannot read (measured on CI macOS)
  printf '  %s: exit %s -> %s (expect ok)\n' "$s" "$rc" "$r"
done | awk '
  /^▼/ {print; next}
  /\(expect / {
    got = ""; want = ""
    if (match($0, /-> *[a-z]+/)) { got = substr($0, RSTART, RLENGTH); sub(/-> */, "", got) }
    if (match($0, /\(expect [a-z]+/)) { want = substr($0, RSTART + 1, RLENGTH - 1); sub(/^expect /, "", want) }
    # A result row (one containing ->) counts as a mismatch even if only the actual or the expected value is unreadable
    # (so an empty expectation, or a test that crashed and left no actual value, cannot slip through)
    if (index($0, "->") && (got == "" || want == "" || got != want)) { bad++; print "❌" $0 }
    else { ok++; print "  " $0 }
    next }
  {print}
  END {printf "\n==== %d as expected / %d mismatches ====\n", ok, bad+0; exit (bad > 0)}'
