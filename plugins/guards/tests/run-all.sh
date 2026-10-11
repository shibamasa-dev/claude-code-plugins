#!/bin/bash
# Regression sweep for this plugin's hooks (runs every tests/test-*.sh and tallies the results).
#
# Usage: bash tests/run-all.sh
# Only rows that don't match the expectation get ❌. Even if the counts look right, stop and read if there is a single ❌.
cd "$(dirname "$0")" || exit 1
for s in test-*.sh; do
  echo; echo "▼ $s"
  bash "$s" 2>&1
  # Don't let a script that crashed midway hide among "0 mismatches" (awk doesn't see the pipe's exit status, so count it as a verdict row)
  rc=$?; [ "$rc" = 0 ] && r=ok || r=crashed
  # Width specifiers (%-56s) can cut a multibyte character in half in some locales, which awk can't read (measured on CI macOS)
  printf '  %s: exit %s -> %s (expect ok)\n' "$s" "$rc" "$r"
done | awk '
  /^▼/ {print; next}
  /\(expect / {
    got = ""; want = ""
    if (match($0, /-> *[a-z]+/)) { got = substr($0, RSTART, RLENGTH); sub(/-> */, "", got) }
    if (match($0, /\(expect [a-z]+/)) { want = substr($0, RSTART + 8, RLENGTH - 8) }
    # A verdict row (one containing ->) counts as a mismatch even if just the actual or the expected value is unreadable
    # (do not let rows with an empty expected value, or a test that crashed and lost its actual value, slip through)
    if (index($0, "->") && (got == "" || want == "" || got != want)) { bad++; print "❌" $0 }
    else { ok++; print "  " $0 }
    next }
  {print}
  END {printf "\n==== %d as expected / %d mismatches ====\n", ok, bad+0; exit (bad > 0)}'
