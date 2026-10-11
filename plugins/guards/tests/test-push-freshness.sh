#!/bin/bash
# Measure the acceptance criteria of push-freshness (bash-guard.py rule 3).
# Create a throwaway git repo in a fresh temp directory, feed JSON to bash-guard.py and look at the verdict.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"

D=$(mktemp -d "${TMPDIR:-/tmp}/gtest.XXXX")
cd "$D" || exit 1

git init -q -b main .   # pin it so the default branch name (init.defaultBranch) doesn't matter
git commit -q --allow-empty -m base
MAINB=$(git rev-parse --abbrev-ref HEAD)
git checkout -q -b feat/x
git commit -q --allow-empty -m work
git checkout -q "$MAINB"
git commit -q --allow-empty -m "main moves on"
# Fake origin/main (no fetch = even if the hook's fetch fails, the behind count uses the ref)
git update-ref refs/remotes/origin/main "$MAINB"
git checkout -q feat/x

probe() {
  printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"%s"}' "$1" "$D" \
    | python3 "$HOOK" 2>/dev/null \
    | python3 -c "
import json,sys
s=sys.stdin.read().strip()
if not s:
    print('allow'); raise SystemExit
d=json.loads(s)
print(d.get('hookSpecificOutput',{}).get('permissionDecision','allow'))"
}

echo '=== behind > 0 ==='
echo "  branch=$(git rev-parse --abbrev-ref HEAD) behind=$(git rev-list --count HEAD..origin/main)"
printf '  %-46s -> %s   (expect deny)\n' 'plain push' "$(probe 'git push -u origin feat/x')"
printf '  %-46s -> %s   (expect deny: a claim alone must not work)\n' 'push with the old marker' "$(probe 'PUSH_FRESHNESS_OK=1 git push -u origin feat/x')"
printf '  %-46s -> %s   (expect deny: other env var names do not pass either)\n' 'push with arbitrary env vars' "$(probe 'SKIP_CHECK=1 FORCE=1 git push -u origin feat/x')"

echo
echo '=== make behind = 0 (create a branch that is up to date) ==='
git checkout -q -b feat/y origin/main
echo "  branch=$(git rev-parse --abbrev-ref HEAD) behind=$(git rev-list --count HEAD..origin/main)"
printf '  %-46s -> %s  (expect allow)\n' 'plain push' "$(probe 'git push -u origin feat/y')"

echo
echo '=== out-of-scope cases (pass through as before) ==='
git checkout -q "$MAINB"
printf '  %-46s -> %s  (expect allow: main-like branches are out of scope)\n' 'push on main' "$(probe "git push -u origin $MAINB")"
printf '  %-46s -> %s  (expect allow: not a push)\n' 'git status' "$(probe 'git status')"

echo
echo '=== main-freshness: marker while main is behind origin/main ==='
git checkout -q -b ahead "$MAINB" && git commit -q --allow-empty -m ahead
git update-ref refs/remotes/origin/main ahead
git checkout -q "$MAINB"
printf '  %-46s -> %s  (expect deny)\n' 'plain commit' "$(probe 'git commit -m x')"
printf '  %-46s -> %s  (expect allow)\n' 'marker at the start of the commit itself' "$(probe 'MAIN_FRESHNESS_OK=1 git commit -m x')"
printf '  %-46s -> %s  (expect deny)\n' 'marker as an echo argument' "$(probe 'echo MAIN_FRESHNESS_OK=1; git commit -m x')"
printf '  %-46s -> %s  (expect deny)\n' 'marker in a comment' "$(probe 'git commit -m x # MAIN_FRESHNESS_OK=1')"

echo
echo '=== default branch other than main (origin/HEAD = origin/develop) ==='
git checkout -q -b develop "$MAINB" && git commit -q --allow-empty -m dev1
git update-ref refs/remotes/origin/develop develop
git commit -q --allow-empty -m dev-local-only   # local develop is ahead of origin/develop (not behind)
git update-ref refs/remotes/origin/develop HEAD~1
git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop
git checkout -q -b feat/d HEAD~1
git checkout -q develop && git commit -q --allow-empty -m dev2 && git update-ref refs/remotes/origin/develop HEAD && git reset -q --hard HEAD~1
git checkout -q feat/d
printf '  %-46s -> %s  (expect deny)\n' 'push a feature branch behind origin/develop' "$(probe 'git push -u origin feat/d')"
git merge -q --no-edit origin/develop
printf '  %-46s -> %s  (expect allow)\n' 'push after merging origin/develop' "$(probe 'git push -u origin feat/d')"
git checkout -q develop
printf '  %-46s -> %s  (expect deny)\n' 'commit on a stale develop' "$(probe 'git commit -m x')"
printf '  %-46s -> %s  (expect allow: the default branch is out of scope)\n' 'push develop' "$(probe 'git push origin develop')"

rm -rf "$D"
