#!/bin/bash
# Runs the research-x unit tests (offline, fixtures only) and prints one verdict row per test file.
cd "$(dirname "$0")" || exit 1
fail=0
for t in test_cli.py test_slack.py test_xai.py; do
  if out=$(python3 -I "$t" 2>&1); then r=ok; else r=failed; fail=1; printf '%s\n' "$out"; fi
  printf '  %s -> %s (expect ok)\n' "$t" "$r"
done
exit $fail
