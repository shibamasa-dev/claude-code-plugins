#!/bin/bash
# Runs classify.sh over the evals.json cases that have a fixture (offline, no manual steps).
# Usage: bash evals/run_evals.sh   (exits 1 if even one case disagrees)
# Fixtures come from real PRs in this repo (how each was taken is in the evals.json source). No made-up values
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CLASSIFY="$HERE/../scripts/classify.sh"
pass=0; fail=0
while IFS=$'\t' read -r id fixture expected reasons; do
  out=$(bash "$CLASSIFY" "$HERE/fixtures/$fixture")
  got=$(printf '%s\n' "$out" | head -1)
  miss=""
  IFS='|' read -r -a want <<< "$reasons"
  for w in "${want[@]}"; do
    [ -n "$w" ] && ! printf '%s\n' "$out" | grep -qF -- "$w" && miss="$miss [$w]"
  done
  if [ "$got" = "$expected" ] && [ -z "$miss" ]; then
    pass=$((pass + 1)); echo "PASS $id: $got"
  else
    fail=$((fail + 1)); echo "FAIL $id: expected $expected / got $got${miss:+ / missing from reasons:$miss}"
    printf '%s\n' "$out" | sed 's/^/    /'
  fi
done < <(jq -r '.[] | select(.fixture) | [.id, .fixture, .expected, ((.expect_reasons // []) | join("|"))] | @tsv' "$HERE/evals.json")
echo "==== PASS $pass / FAIL $fail ===="
[ "$fail" = 0 ] && [ "$pass" -gt 0 ]
