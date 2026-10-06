#!/bin/bash
# REPO_STRUCTURE_SPEC が存在しないパスを指すとき（明示的に外したとき）は何も出さずに通すこと。
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/repo-structure-guard.py"
R=$(mktemp -d "${TMPDIR:-/tmp}/rsg-nospec.XXXX"); mkdir -p "$R/docs" "$R/scripts"; git -C "$R" init -q
probe() {
  out=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"},"cwd":"%s"}' "$1" "$R" \
        | REPO_STRUCTURE_SPEC="$2" python3 "$H"); rc=$?
  [ $rc = 0 ] && [ -z "$out" ] && echo silent || echo "rc=$rc out=${#out}"
}
row() { printf '  %-56s -> %-6s (%s 期待)\n' "$1" "$2" "$3"; }
echo '=== ルールファイルが無い ==='
row 'docs/ 直下の新規 .md'             "$(probe "$R/docs/new.md" /nonexistent/repo-structure.md)" silent
row 'scripts/ 直下の新規スクリプト'    "$(probe "$R/scripts/new.sh" /nonexistent/repo-structure.md)" silent
