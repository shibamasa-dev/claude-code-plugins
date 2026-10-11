#!/bin/bash
# How repo-structure-guard finds its rule file: env var → the repo's .claude/rules → the user's ~/.claude/rules;
# if none exists, do nothing (opt-in).
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/repo-structure-guard.py"
R=$(mktemp -d "${TMPDIR:-/tmp}/rsg-lookup.XXXX"); mkdir -p "$R/home" "$R/repo/docs" "$R/repo/scripts"
git -C "$R/repo" init -q
probe() {   # $1 = write target, the rest is passed to env (environment overrides)
  f=$1; shift
  out=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$f" \
        | env -u REPO_STRUCTURE_SPEC HOME="$R/home" "$@" python3 "$H") || { echo error; return; }
  case "$out" in *'"deny"'*) echo deny ;; '') echo silent ;; *) echo other ;; esac
}
FAIL=0
row() { printf '  %-56s -> %-6s (expect %s)\n' "$1" "$2" "$3"; [ "$2" = "$3" ] || FAIL=1; }
# Make a rule that allows exactly one .md directly under docs/ (the allowed name tells which rule was used)
spec() {
  mkdir -p "$(dirname "$1")"
  cat > "$1" <<SPEC
<!-- guard:docs-allow-filenames -->
- $2
<!-- /guard:docs-allow-filenames -->
<!-- guard:docs-subfolders -->
- spec: specs
<!-- /guard:docs-subfolders -->
<!-- guard:script-extensions -->
- .sh
<!-- /guard:script-extensions -->
SPEC
}
echo '=== no rule file anywhere (default) ==='
row 'new .md directly under docs/'                 "$(probe "$R/repo/docs/new.md")" silent
row 'new script directly under scripts/'           "$(probe "$R/repo/scripts/new.sh")" silent
echo '=== only the user rule exists ==='
spec "$R/home/.claude/rules/repo-structure.md" user.md
row '.md not allowed by the user rule'             "$(probe "$R/repo/docs/new.md")" deny
row '.md allowed by the user rule'                 "$(probe "$R/repo/docs/user.md")" silent
echo '=== a repo rule too (wins over the user rule) ==='
spec "$R/repo/.claude/rules/repo-structure.md" repo.md
row '.md allowed by the repo rule'                 "$(probe "$R/repo/docs/repo.md")" silent
row '.md allowed only by the user rule'            "$(probe "$R/repo/docs/user.md")" deny
echo '=== does not apply to another repo ==='
mkdir -p "$R/other/docs"; git -C "$R/other" init -q
row 'another repo uses the user rule'              "$(probe "$R/other/docs/user.md")" silent
row 'repo.md in another repo'                      "$(probe "$R/other/docs/repo.md")" deny
echo '=== environment variable (highest priority) ==='
spec "$R/env.md" env.md
row '.md allowed by the REPO_STRUCTURE_SPEC rule'  "$(probe "$R/repo/docs/env.md" REPO_STRUCTURE_SPEC="$R/env.md")" silent
row 'with REPO_STRUCTURE_SPEC the repo rule is ignored' "$(probe "$R/repo/docs/repo.md" REPO_STRUCTURE_SPEC="$R/env.md")" deny
row 'env var pointing to a missing path = off'     "$(probe "$R/repo/docs/new.md" REPO_STRUCTURE_SPEC=/nonexistent/x.md)" silent
rm -rf "$R"
exit $FAIL
