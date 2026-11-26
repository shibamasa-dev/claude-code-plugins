#!/bin/bash
# Regression sweep for this plugin: runs every tests/test-*.sh and tallies the verdict rows.
#
# Usage: bash tests/run-all.sh [extra scripts...]   (extra scripts are relative to tests/ and run after test-*.sh)
#
# Every plugins/<name>/tests/run-all.sh is this same file (.github/scripts/check-repo.py fails when one differs),
# so change all of them together. It is a copy rather than one shared script so that the tests of an installed
# plugin, which has no .github/ next to it, still run.
#
# Verdict rows: a line containing "(expect " is a verdict row. <got> is the first word after the last "->"
# before "(expect", <want> the first word after "(expect " (ending at a space, ":" or ")"). Words and numbers
# both work. The row is a mismatch when there is no "->", when either side is empty, or when they differ.
# Each script also gets a row for its own exit status, so a script that crashes or exits non-zero is a mismatch.
# Only rows that don't match get ❌. Even if the totals look right, stop and read if there is a single ❌.
cd "$(dirname "$0")" || exit 1
for s in test-*.sh "$@"; do
  echo; echo "▼ $s"
  bash "$s" 2>&1
  # awk doesn't see the exit status of the scripts in the pipe, so turn it into a verdict row
  rc=$?; [ "$rc" = 0 ] && r=ok || r=crashed
  # No width specifiers (%-56s) here: in some locales they cut a multibyte character in half (seen on CI macOS)
  printf '  %s: exit %s -> %s (expect ok)\n' "$s" "$rc" "$r"
done | LC_ALL=C awk '
  # LC_ALL=C: compare bytes, so multibyte text in a row (or a byte sequence the locale rejects) cannot break parsing
  index($0, "(expect ") {
    i = index($0, "(expect ")
    pre = substr($0, 1, i - 1); post = substr($0, i + 8)
    j = 0
    while ((k = index(substr(pre, j + 1), "->")) > 0) j += k + 1   # j ends on the ">" of the last "->"
    got = ""; want = ""
    if (j > 0) { got = substr(pre, j + 1); sub(/^[ \t]+/, "", got); sub(/[ \t].*$/, "", got) }
    sub(/^[ \t]+/, "", post)
    if (match(post, /^[^ \t:)]+/)) want = substr(post, 1, RLENGTH)
    if (got == "" || want == "" || got != want) { bad++; print "❌" $0 }
    else { ok++; print "  " $0 }
    next }
  {print}
  END {printf "\n==== %d as expected / %d mismatches ====\n", ok, bad+0; exit (bad > 0)}'
