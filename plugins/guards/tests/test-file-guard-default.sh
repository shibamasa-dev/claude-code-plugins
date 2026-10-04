#!/bin/bash
# FILE_GUARD_SPEC も ~/.claude/rules/repo-structure.md も無いとき、プラグイン同梱の既定で判定すること。
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/file-guard.py"
R=$(mktemp -d "${TMPDIR:-/tmp}/fg-default.XXXX"); mkdir -p "$R/home" "$R/repo/docs" "$R/repo/scripts"
probe() {
  out=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$1" \
        | env -u FILE_GUARD_SPEC HOME="$R/home" python3 "$H")
  case "$out" in *'"deny"'*) echo deny ;; '') echo silent ;; *) echo other ;; esac
}
row() { printf '  %-56s -> %-6s (%s 期待)\n' "$1" "$2" "$3"; }
echo '=== ユーザーの規約が無い（プラグイン既定） ==='
row 'docs/ 直下の新規 .md'             "$(probe "$R/repo/docs/new.md")" deny
row 'docs/README.md'                   "$(probe "$R/repo/docs/README.md")" silent
row 'scripts/ 直下の新規スクリプト'    "$(probe "$R/repo/scripts/new.sh")" deny
rm -rf "$R"
