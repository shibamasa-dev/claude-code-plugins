#!/bin/bash
# Fail if a plugin's contents changed but its plugin.json version is still the base version.
# With the same version, `claude plugin update` treats the plugin as up to date and doesn't replace it (measured 2026-10-04).
# Tests (tests/), README.md / README.ja.md and CHANGELOG don't affect users, so they are exempt. New plugins not in base are exempt too.
# A plugin whose version was bumped fails unless CHANGELOG.md has a heading for that version (## [x.y.z] - YYYY-MM-DD at line start); a missing file fails too.
# Usage: check-version-bump.sh <base ref> (e.g. origin/main)
set -u
base=$1
fail=0
for d in plugins/*/; do
  p=${d%/}
  [ -f "$p/.claude-plugin/plugin.json" ] || continue
  changed=$(git diff --name-only "$base"...HEAD -- "$p" ":(exclude)$p/tests" ":(exclude)$p/README.md" ":(exclude)$p/README.ja.md" ":(exclude)$p/CHANGELOG.md")
  [ -n "$changed" ] || continue
  old=$(git show "$base:$p/.claude-plugin/plugin.json" 2>/dev/null | jq -r '.version // empty')
  [ -n "$old" ] || continue
  new=$(jq -r '.version // empty' "$p/.claude-plugin/plugin.json")
  # Fail on a lowered version as well as an unchanged one (sort -V orders SemVer; new must come last and differ from old)
  if [ "$old" = "$new" ] || [ "$(printf '%s\n%s\n' "$old" "$new" | sort -V | tail -1)" != "$new" ]; then
    echo "::error file=$p/.claude-plugin/plugin.json::$p contents changed but its version was not bumped ($old -> $new; plugin update won't install it otherwise)"
    printf '%s\n' "$changed" | sed 's/^/  changed: /'
    fail=1
  elif ! awk -v h="## [$new] - " 'index($0, h) == 1 && substr($0, length(h) + 1) ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]([[:space:]]|$)/ { found = 1 } END { exit !found }' "$p/CHANGELOG.md" 2>/dev/null; then
    # Count only headings at line start and check the date too (so text in the body, a heading without a date, or a deleted CHANGELOG.md doesn't pass)
    echo "::error file=$p/CHANGELOG.md::$p version was bumped to $new but CHANGELOG.md has no \"## [$new] - YYYY-MM-DD\" heading"
    fail=1
  else
    echo "$p: $old -> $new"
  fi
done
exit $fail
