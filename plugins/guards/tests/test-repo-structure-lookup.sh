#!/bin/bash
# repo-structure-guard のルールファイルの探し方：環境変数 → リポの .claude/rules → ユーザーの ~/.claude/rules、
# どれも無ければ何もしない（オプトイン）。
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/repo-structure-guard.py"
R=$(mktemp -d "${TMPDIR:-/tmp}/rsg-lookup.XXXX"); mkdir -p "$R/home" "$R/repo/docs" "$R/repo/scripts"
git -C "$R/repo" init -q
probe() {   # $1 = 書き込み先、残りは env に渡す（環境変数の上書き）
  f=$1; shift
  out=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$f" \
        | env -u REPO_STRUCTURE_SPEC HOME="$R/home" "$@" python3 "$H") || { echo error; return; }
  case "$out" in *'"deny"'*) echo deny ;; '') echo silent ;; *) echo other ;; esac
}
FAIL=0
row() { printf '  %-56s -> %-6s (%s 期待)\n' "$1" "$2" "$3"; [ "$2" = "$3" ] || FAIL=1; }
# docs/ 直下に許す .md を1つだけ書いたルールを作る（どのルールが使われたかを許すファイル名で見分ける）
spec() {
  mkdir -p "$(dirname "$1")"
  cat > "$1" <<SPEC
<!-- guard:docs-allow-filenames -->
- $2
<!-- /guard:docs-allow-filenames -->
<!-- guard:docs-subfolders -->
- spec: 仕様
<!-- /guard:docs-subfolders -->
<!-- guard:script-extensions -->
- .sh
<!-- /guard:script-extensions -->
SPEC
}
echo '=== ルールファイルがどこにも無い（既定） ==='
row 'docs/ 直下の新規 .md'                  "$(probe "$R/repo/docs/new.md")" silent
row 'scripts/ 直下の新規スクリプト'         "$(probe "$R/repo/scripts/new.sh")" silent
echo '=== ユーザーのルールだけある ==='
spec "$R/home/.claude/rules/repo-structure.md" user.md
row 'ユーザーのルールで許していない .md'    "$(probe "$R/repo/docs/new.md")" deny
row 'ユーザーのルールで許した .md'          "$(probe "$R/repo/docs/user.md")" silent
echo '=== リポのルールもある（ユーザーより優先） ==='
spec "$R/repo/.claude/rules/repo-structure.md" repo.md
row 'リポのルールで許した .md'              "$(probe "$R/repo/docs/repo.md")" silent
row 'ユーザーのルールだけで許した .md'      "$(probe "$R/repo/docs/user.md")" deny
echo '=== 別のリポには効かない ==='
mkdir -p "$R/other/docs"; git -C "$R/other" init -q
row '別のリポではユーザーのルール'          "$(probe "$R/other/docs/user.md")" silent
row '別のリポで repo.md'                    "$(probe "$R/other/docs/repo.md")" deny
echo '=== 環境変数（いちばん優先） ==='
spec "$R/env.md" env.md
row 'REPO_STRUCTURE_SPEC のルールで許した .md' "$(probe "$R/repo/docs/env.md" REPO_STRUCTURE_SPEC="$R/env.md")" silent
row 'REPO_STRUCTURE_SPEC があるとリポのルールは見ない' "$(probe "$R/repo/docs/repo.md" REPO_STRUCTURE_SPEC="$R/env.md")" deny
row '環境変数が無いパスを指す＝外す'        "$(probe "$R/repo/docs/new.md" REPO_STRUCTURE_SPEC=/nonexistent/x.md)" silent
rm -rf "$R"
exit $FAIL
