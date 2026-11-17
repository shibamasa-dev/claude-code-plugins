#!/bin/bash
# repo-structure-guard reads the repo's rule file from the default branch (origin/<default>), so a branch cannot loosen
# the layout rule it is judged by. Missing there -> the user's ~/.claude/rules file, never the working tree.
# Without an origin remote it reads the working tree and says so on stderr.
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/repo-structure-guard.py"
R=$(mktemp -d "${TMPDIR:-/tmp}/rsg-base.XXXX") || exit 1
trap 'rm -rf "$R"' EXIT
mkdir -p "$R/home"
spec() { mkdir -p "$(dirname "$1")"; printf '%s\n' '<!-- guard:docs-allow-filenames -->' "- $2" '<!-- /guard:docs-allow-filenames -->' \
  '<!-- guard:docs-subfolders -->' '- spec: specs' '<!-- /guard:docs-subfolders -->' \
  '<!-- guard:script-extensions -->' '- .sh' '<!-- /guard:script-extensions -->' > "$1"; }
# repo <name> <allowed name on the default branch, or empty> <allowed name on the branch> [origin|none] -> the clone
repo() {
  d="$R/$1"; w="$d/work"; mkdir -p "$w/docs" || exit 1; g() { git -C "$w" -c user.name=t -c user.email=t@t "$@"; }
  b=${B:-main}; g init -q -b "$b"; echo x > "$w/README.md"
  [ -n "$2" ] && spec "$w/.claude/rules/repo-structure.md" "$2"
  g add -A; g commit -qm base
  if [ "${4:-origin}" = origin ]; then
    git init -q --bare -b "$b" "$d/origin.git" && g remote add origin "$d/origin.git" && g push -q origin "$b" && g fetch -q origin || exit 1
  fi
  g checkout -qb feat; spec "$w/.claude/rules/repo-structure.md" "$3"; g add -A; g commit -qm loosen; echo "$w"
}
probe() { printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$1" \
  | env -u REPO_STRUCTURE_SPEC HOME="$R/home" python3 "$H" 2>/dev/null | grep -q '"deny"' && echo deny || echo silent; }
FAIL=0
row() { printf '  %-60s -> %-6s (expect %s)\n' "$1" "$2" "$3"; [ "$2" = "$3" ] || FAIL=1; }

w=$(repo loosen base.md sneaky.md)
row 'branch loosens the rule: the default branch rule still denies' "$(probe "$w/docs/sneaky.md")" deny
row 'name allowed on the default branch'                           "$(probe "$w/docs/base.md")" silent
w=$(repo new '' sneaky.md)
row 'rule only on the branch, no user rule: no check'              "$(probe "$w/docs/other.md")" silent
spec "$R/home/.claude/rules/repo-structure.md" user.md
row 'rule only on the branch: the user rule applies'               "$(probe "$w/docs/sneaky.md")" deny
rm -rf "$R/home/.claude"
w=$(repo noorigin '' wt.md none)
row 'no origin: the working tree rule applies'                     "$(probe "$w/docs/other.md")" deny
note=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$w/docs/other.md" \
  | env -u REPO_STRUCTURE_SPEC HOME="$R/home" python3 "$H" 2>&1 >/dev/null)
row 'no origin: a one-line note on stderr'                         "$(printf '%s' "$note" | grep -q 'no origin remote' && echo note || echo quiet)" note
w=$(B=trunk repo trunk base.md sneaky.md); git -C "$w" remote set-head origin -d 2>/dev/null   # as with git < 2.48
row 'default branch trunk (no local origin/HEAD): its rule denies'  "$(probe "$w/docs/sneaky.md")" deny
w=$(repo single base.md sneaky.md); git -C "$w" push -q origin feat; git clone -q --single-branch -b feat "$R/single/origin.git" "$R/single/clone"
row 'single-branch clone: the default branch rule is fetched'     "$(probe "$R/single/clone/docs/sneaky.md")" deny
w=$(repo unreadable '' sneaky.md); git -C "$w" remote set-url origin "$R/missing.git"; git -C "$w" update-ref -d refs/remotes/origin/main
row 'origin unreadable: the working tree rule is not used'         "$(probe "$w/docs/other.md")" silent
exit $FAIL
