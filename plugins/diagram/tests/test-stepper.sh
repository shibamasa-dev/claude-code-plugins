#!/bin/bash
# Runs the node:test suites in tests/*.test.mjs and prints one verdict row per test (run-all.sh tallies them).
# Needs Node.js 20 or later. Without node the script exits non-zero, so run-all.sh reports a mismatch.
set -u
cd "$(dirname "$0")" || exit 1
command -v node >/dev/null || { echo "node not found: the stepper tests need Node.js 20 or later"; exit 1; }
out=$(node --test --test-reporter=tap ./*.test.mjs 2>&1); rc=$?
# Top-level TAP results only ("ok N - name" / "not ok N - name"), one row each
printf '%s\n' "$out" | awk '
  /^ok [0-9]+ - / { sub(/^ok [0-9]+ - /, ""); printf "  %s -> ok (expect ok)\n", $0 }
  /^not ok [0-9]+ - / { sub(/^not ok [0-9]+ - /, ""); printf "  %s -> failed (expect ok)\n", $0 }'
[ "$rc" = 0 ] || printf '%s\n' "$out"
exit "$rc"
