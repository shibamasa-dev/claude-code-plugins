#!/bin/bash
# classify.sh を evals.json の fixture 付きケースで回す（オフライン・手作業ゼロ）。
# 使い方: bash evals/run_evals.sh   （1 件でも食い違えば exit 1）
# fixture はこのリポの実在の PR から取ったもの（取り方は evals.json の source）。作った値は入れない
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
    fail=$((fail + 1)); echo "FAIL $id: 期待 $expected / 実測 $got${miss:+ / 理由に無い:$miss}"
    printf '%s\n' "$out" | sed 's/^/    /'
  fi
done < <(jq -r '.[] | select(.fixture) | [.id, .fixture, .expected, ((.expect_reasons // []) | join("|"))] | @tsv' "$HERE/evals.json")
echo "==== PASS $pass 件 / FAIL $fail 件 ===="
[ "$fail" = 0 ] && [ "$pass" -gt 0 ]
