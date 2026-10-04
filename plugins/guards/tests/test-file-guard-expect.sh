#!/bin/bash
# file-guard.py の16ケースを期待値つきで検証する（規約の単一定義化で挙動が変わっていないこと）。
cd "$(dirname "$0")" || exit 1
bash ./test-file-guard.sh /tmp/fg-now.txt
# paste は '-' を渡さないと標準入力（下のヒアドキュメント）を読まない。無いと期待値が空のまま並ぶ
paste -d'|' <(tail -n +2 /tmp/fg-now.txt) - <<'EXPECT' | while IFS='|' read -r got want; do
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
EXPECT
  g=$(echo "$got" | awk '{print $1}'); label=$(echo "$got" | cut -d' ' -f2-)
  printf '  %-56s -> %-5s (%s 期待)\n' "$(echo $label)" "$g" "$(echo $want)"
done
