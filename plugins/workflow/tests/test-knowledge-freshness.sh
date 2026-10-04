#!/bin/bash
# knowledge-freshness.py の受け入れ基準を実測する。
# 本物の ~/.claude を触らないよう、フィクスチャ木を作って ROOT を差し替えた複製で回す。
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/knowledge-freshness.py"
F=/tmp/kf-fixture
rm -rf "$F"
mkdir -p "$F/rules" "$F/reference" "$F/skills/alpha" "$F/skills/beta"

# 期限切れ（過去）
printf -- '---\npaths:\n  - "**/*.md"\nlast_reviewed: 2026-01-01\nreview_after: 2026-08-01\n---\n\n# 期限切れ\n' \
  > "$F/rules/expired.md"
# 期限内（未来）
printf -- '---\nlast_reviewed: 2026-09-01\nreview_after: 2027-03-01\n---\n\n# 期限内\n' \
  > "$F/rules/fresh.md"
# frontmatter 自体が無い
printf -- '# 鮮度未設定\n本文だけ。\n' > "$F/reference/no-frontmatter.md"
# frontmatter はあるが last_reviewed が無い
printf -- '---\nname: beta\ndescription: x\n---\n\n# キー欠け\n' > "$F/skills/beta/SKILL.md"
# YAML が壊れている
printf -- '---\nname: alpha\nlast_reviewed: "壊れた値\nreview_after: ????\n---\n\n# 壊れ\n' \
  > "$F/skills/alpha/SKILL.md"

# ROOT だけ差し替えた複製を作る
sed "s|os.path.expanduser(\"~/.claude\")|\"$F\"|" "$HOOK" > "$F/hook.py"

run() { echo '{"hook_event_name":"SessionStart"}' | python3 "$F/hook.py" 2>"$F/err"; echo "|exit=$?"; }

echo '=== ケース1: 期限切れ・未設定・壊れが混在 ==='
OUT=$(run)
CODE=${OUT##*|}
BODY=${OUT%|*}
echo "  $CODE  (exit=0 期待: BLOCK しない)"
echo "  stderr: $(wc -c <"$F/err" | tr -d ' ')B (0 期待)"
python3 - "$BODY" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
ctx = d["hookSpecificOutput"]["additionalContext"]
print("  --- 注入内容 ---")
for line in ctx.splitlines():
    print("   ", line)
PY

echo
echo '=== ケース2: 全部期限内なら完全に silent ==='
rm -f "$F/rules/expired.md" "$F/reference/no-frontmatter.md" "$F/skills/beta/SKILL.md" "$F/skills/alpha/SKILL.md"
rmdir "$F/skills/alpha" "$F/skills/beta" 2>/dev/null
OUT2=$(run)
echo "  ${OUT2##*|}  (exit=0 期待)"
echo "  stdout: ${#OUT2} 文字 → 実体 $(( ${#OUT2} - ${#CODE} - 1 ))B (0 期待)"

echo
echo '=== ケース3: ディレクトリごと消えても落ちない ==='
rm -rf "$F/rules" "$F/reference" "$F/skills"
OUT3=$(run)
echo "  ${OUT3##*|}  (exit=0 期待)"

rm -rf "$F"
