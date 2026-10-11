#!/bin/bash
# When REPO_STRUCTURE_SPEC points to a missing path (explicitly turned off), pass silently.
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/repo-structure-guard.py"
R=$(mktemp -d "${TMPDIR:-/tmp}/rsg-nospec.XXXX"); mkdir -p "$R/docs" "$R/scripts"; git -C "$R" init -q
probe() {
  out=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"},"cwd":"%s"}' "$1" "$R" \
        | REPO_STRUCTURE_SPEC="$2" python3 "$H"); rc=$?
  [ $rc = 0 ] && [ -z "$out" ] && echo silent || echo "rc=$rc out=${#out}"
}
row() { printf '  %-56s -> %-6s (expect %s)\n' "$1" "$2" "$3"; }
echo '=== no rule file ==='
row 'new .md directly under docs/'             "$(probe "$R/docs/new.md" /nonexistent/repo-structure.md)" silent
row 'new script directly under scripts/'       "$(probe "$R/scripts/new.sh" /nonexistent/repo-structure.md)" silent
