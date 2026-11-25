#!/bin/bash
# Runs the certfill.py tests (offline, official forms and synthetic values only) and prints one verdict row.
cd "$(dirname "$0")" || exit 1
if out=$(python3 -I test_certfill.py 2>&1); then r=ok; else r=failed; fi
printf '%s\n' "$out" | tail -n 25
printf '  test_certfill.py -> %s (expect ok)\n' "$r"
[ "$r" = ok ]
