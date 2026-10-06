#!/bin/bash
# push-freshness（bash-guard.py ルール3）の受け入れ基準を実測する。
# 使い捨ての git リポを /tmp に作り、bash-guard.py に JSON を食わせて判定を見る。
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"

rm -rf /tmp/gtest
mkdir -p /tmp/gtest
cd /tmp/gtest || exit 1

git init -q -b main .   # 既定ブランチ名（init.defaultBranch）に左右されないよう固定する
git commit -q --allow-empty -m base
MAINB=$(git rev-parse --abbrev-ref HEAD)
git checkout -q -b feat/x
git commit -q --allow-empty -m work
git checkout -q "$MAINB"
git commit -q --allow-empty -m "main moves on"
# origin/main を疑似的に作る（fetch はさせない＝hook の fetch は失敗しても behind 計算は ref を見る）
git update-ref refs/remotes/origin/main "$MAINB"
git checkout -q feat/x

probe() {
  printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"/tmp/gtest"}' "$1" \
    | python3 "$HOOK" 2>/dev/null \
    | python3 -c "
import json,sys
s=sys.stdin.read().strip()
if not s:
    print('allow'); raise SystemExit
d=json.loads(s)
print(d.get('hookSpecificOutput',{}).get('permissionDecision','allow'))"
}

echo '=== behind > 0 の状態 ==='
echo "  branch=$(git rev-parse --abbrev-ref HEAD) behind=$(git rev-list --count HEAD..origin/main)"
printf '  %-46s -> %s   (deny 期待)\n' '素の push' "$(probe 'git push -u origin feat/x')"
printf '  %-46s -> %s   (deny 期待: 申告が効かないこと)\n' '旧マーカー付き push' "$(probe 'PUSH_FRESHNESS_OK=1 git push -u origin feat/x')"
printf '  %-46s -> %s   (deny 期待: 別名の環境変数でも通らない)\n' '適当な環境変数付き push' "$(probe 'SKIP_CHECK=1 FORCE=1 git push -u origin feat/x')"

echo
echo '=== behind = 0 にする（取り込み済みブランチを作る） ==='
git checkout -q -b feat/y origin/main
echo "  branch=$(git rev-parse --abbrev-ref HEAD) behind=$(git rev-list --count HEAD..origin/main)"
printf '  %-46s -> %s  (allow 期待)\n' '素の push' "$(probe 'git push -u origin feat/y')"

echo
echo '=== 対象外のケース（従来どおり素通り） ==='
git checkout -q "$MAINB"
printf '  %-46s -> %s  (allow 期待: main 系は対象外)\n' 'main で push' "$(probe "git push -u origin $MAINB")"
printf '  %-46s -> %s  (allow 期待: push 以外)\n' 'git status' "$(probe 'git status')"

echo
echo '=== main-freshness: main が origin/main より遅れている状態のマーカー ==='
git checkout -q -b ahead "$MAINB" && git commit -q --allow-empty -m ahead
git update-ref refs/remotes/origin/main ahead
git checkout -q "$MAINB"
printf '  %-46s -> %s  (deny 期待)\n' '素の commit' "$(probe 'git commit -m x')"
printf '  %-46s -> %s  (allow 期待)\n' 'commit 自身の先頭にマーカー' "$(probe 'MAIN_FRESHNESS_OK=1 git commit -m x')"
printf '  %-46s -> %s  (deny 期待)\n' 'マーカーを echo の引数に' "$(probe 'echo MAIN_FRESHNESS_OK=1; git commit -m x')"
printf '  %-46s -> %s  (deny 期待)\n' 'マーカーをコメントに' "$(probe 'git commit -m x # MAIN_FRESHNESS_OK=1')"

rm -rf /tmp/gtest
