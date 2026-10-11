#!/bin/bash
# Check repo-structure-guard.py's 19 cases against expected values (behavior unchanged by single-sourcing the rules).
cd "$(dirname "$0")" || exit 1
NOW=$(mktemp "${TMPDIR:-/tmp}/rsg-now.XXXX"); trap 'rm -f "$NOW"' EXIT
bash ./test-repo-structure.sh "$NOW"
# paste only reads stdin (the heredoc below) when given '-'. Without it the expected values come out empty
paste -d'|' <(tail -n +2 "$NOW") - <<'EXPECT' | while IFS='|' read -r got want; do
deny
allow
deny
allow
allow
allow
deny
deny
deny
allow
allow
allow
allow
allow
deny
allow
deny
deny
deny
EXPECT
  g=$(echo "$got" | awk '{print $1}'); label=$(echo "$got" | cut -d' ' -f2-)
  printf '  %-56s -> %-5s (expect %s)\n' "$(echo $label)" "$g" "$(echo $want)"
done
