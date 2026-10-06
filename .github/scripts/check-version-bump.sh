#!/bin/bash
# プラグインの中身を変えたのに plugin.json の version が base のままなら落とす。
# version が同じだと `claude plugin update` が「最新」と判断して中身を入れ替えない（実測 2026-10-04）。
# テスト（tests/）・README・CHANGELOG は利用者の動作に関係しないので対象外。base に無い新しいプラグインも対象外。
# version を上げたプラグインに CHANGELOG.md があれば、同じ版の見出し（## [x.y.z]）が無いと落とす。
# 使い方: check-version-bump.sh <base の ref>（例: origin/main）
set -u
base=$1
fail=0
for d in plugins/*/; do
  p=${d%/}
  [ -f "$p/.claude-plugin/plugin.json" ] || continue
  changed=$(git diff --name-only "$base"...HEAD -- "$p" ":(exclude)$p/tests" ":(exclude)$p/README.md" ":(exclude)$p/CHANGELOG.md")
  [ -n "$changed" ] || continue
  old=$(git show "$base:$p/.claude-plugin/plugin.json" 2>/dev/null | jq -r '.version // empty')
  [ -n "$old" ] || continue
  new=$(jq -r '.version // empty' "$p/.claude-plugin/plugin.json")
  # 据え置きだけでなく下げたのも落とす（sort -V で SemVer の順に並べ、new が最後に来て old と違うこと）
  if [ "$old" = "$new" ] || [ "$(printf '%s\n%s\n' "$old" "$new" | sort -V | tail -1)" != "$new" ]; then
    echo "::error file=$p/.claude-plugin/plugin.json::$p の中身が変わったのに version が上がっていない（$old -> $new。上げないと plugin update で入らない）"
    printf '%s\n' "$changed" | sed 's/^/  変更: /'
    fail=1
  elif [ -f "$p/CHANGELOG.md" ] && ! grep -qF "## [$new]" "$p/CHANGELOG.md"; then
    echo "::error file=$p/CHANGELOG.md::$p の version を $new に上げたのに CHANGELOG.md に「## [$new]」の見出しが無い"
    fail=1
  else
    echo "$p: $old -> $new"
  fi
done
exit $fail
