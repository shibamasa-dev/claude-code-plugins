#!/bin/bash
# repo-structure-guard.py の19ケースを期待値つきで検証する（規約の単一定義化で挙動が変わっていないこと）。
cd "$(dirname "$0")" || exit 1
NOW=$(mktemp "${TMPDIR:-/tmp}/rsg-now.XXXX"); trap 'rm -f "$NOW"' EXIT
bash ./test-repo-structure.sh "$NOW"
# paste は '-' を渡さないと標準入力（下のヒアドキュメント）を読まない。無いと期待値が空のまま並ぶ
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
  printf '  %-56s -> %-5s (%s 期待)\n' "$(echo $label)" "$g" "$(echo $want)"
done
