#!/bin/bash
# full-test-gate reads .claude/full-test.json from the default branch (origin/<default>), so a branch cannot change the
# command that records a pass or drop the gate that blocks its own release. Without an origin remote it reads the working
# tree and says so on stderr. `run --working-tree` tries the working tree's config and never records.
set -u
# A caller's repo-selecting git variables (a git hook sets GIT_DIR) must not point the fixtures at the caller's repo
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/full-test-gate.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/ftg-test.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
export FULL_TEST_STATE_DIR="$T/state"
BASE_CFG='{"command": "echo base > ran", "paths": ["src"], "gate": ["build-release"]}'
g() { git -C "$1" -c user.name=t -c user.email=t@t "${@:2}"; }
# repo <name> <config on the default branch, or empty> [origin|none] -> path of a clone on branch feat
repo() {
  d="$T/$1"; w="$d/work"; mkdir -p "$w/src" "$w/.claude" || exit 1
  g "$w" init -q -b "${B:-main}" && echo a > "$w/src/a"
  [ -n "$2" ] && printf '%s\n' "$2" > "$w/.claude/full-test.json"
  g "$w" add src .claude 2>/dev/null; g "$w" commit -qm base
  if [ "${3:-origin}" = origin ]; then
    git init -q --bare -b "${B:-main}" "$d/origin.git" && g "$w" remote add origin "$d/origin.git" \
      && g "$w" push -q origin "${B:-main}" && g "$w" fetch -q origin || exit 1
  fi
  g "$w" checkout -qb feat; echo "$w"
}
branch_cfg() { printf '%s\n' "$2" > "$1/.claude/full-test.json"; g "$1" add .claude; g "$1" commit -qm cfg; }
ran() { cat "$1/ran" 2>/dev/null || echo none; }
recorded() { ls "$FULL_TEST_STATE_DIR" 2>/dev/null | grep -q . && echo recorded || echo norecord; }
# pre <dir> [VAR=value ...] [command] -> deny / silent for a PreToolUse Bash call (default command ./build-release.sh)
pre() { dir=$1; shift; envs=(); while [ $# -gt 0 ] && [[ $1 == *=* ]]; do envs+=("$1"); shift; done
        printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","cwd":"%s","tool_input":{"command":"%s"}}' "$dir" "${1:-./build-release.sh}" \
        | env "${envs[@]+"${envs[@]}"}" python3 "$H" 2>/dev/null | grep -q '"deny"' && echo deny || echo silent; }
# net: whether the ssh transport ran (GIT_SSH_COMMAND touches $T/net)
NET_ENV="GIT_SSH_COMMAND=touch $T/net; false"
net() { [ -f "$T/net" ] && echo network || echo cached; rm -f "$T/net"; }
fail=0
row() { printf '  %-60s -> %s (expect %s)\n' "$1" "$2" "$3"; [ "$2" = "$3" ] || fail=1; }

w=$(repo changed "$BASE_CFG"); branch_cfg "$w" '{"command": "echo branch > ran", "paths": ["src"], "gate": []}'
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'branch changed command: run uses the default branch command' "$(ran "$w")" base
echo b >> "$w/src/a"   # an unverified change in the target paths
row 'branch dropped the gate: release is still gated'           "$(pre "$w")" deny
g "$w" checkout -q -- src

rm -rf "$FULL_TEST_STATE_DIR"; rm -f "$w/ran"; (cd "$w" && python3 "$H" run --working-tree >/dev/null 2>&1)
row 'run --working-tree runs the working tree command'           "$(ran "$w")" branch
row 'run --working-tree never records'                           "$(recorded)" norecord

w=$(repo absent ''); branch_cfg "$w" "$BASE_CFG"
row 'config only on the branch: not opted in (status)'           "$(cd "$w" && python3 "$H" status | grep -q 'Not configured' && echo off || echo on)" off
row 'config only on the branch: release not gated'               "$(pre "$w")" silent

w=$(repo noorigin '{"command": "echo base > ran", "paths": ["src"], "base": "main"}' none); rm -rf "$FULL_TEST_STATE_DIR"
err=$(cd "$w" && python3 "$H" run 2>&1 >/dev/null)
row 'no origin: the working tree config is run'                  "$(ran "$w")" base
row 'no origin: a one-line note on stderr'                       "$(printf '%s' "$err" | grep -q 'no origin remote' && echo note || echo quiet)" note

# default branch trunk, no local origin/HEAD (git < 2.48 does not create it on fetch), and a non-default origin/main
# holding the branch's config: origin is asked for the name, so main does not supply the config
w=$(B=trunk repo trunk "$BASE_CFG"); branch_cfg "$w" '{"command": "echo branch > ran", "paths": ["src"], "gate": []}'
g "$w" push -q origin feat:main && g "$w" fetch -q origin && g "$w" remote set-head origin -d 2>/dev/null
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'default branch trunk: run uses its command'                  "$(ran "$w")" base

# single-branch clone of feat: origin/main is fetched into its ref (the clone's refspec does not cover it)
d="$T/single"; g "$T/changed/work" push -q origin feat && git clone -q --single-branch -b feat "$T/changed/origin.git" "$d" || exit 1
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$d" && python3 "$H" run >/dev/null 2>&1)
row 'single-branch clone: run uses the default branch command'     "$(ran "$d")" base

# --working-tree needs no comparison base (no origin, no base key)
w=$(repo wtnobase "$BASE_CFG" none); rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run --working-tree >/dev/null 2>&1)
row 'run --working-tree without a comparison base still runs'      "$(ran "$w")" base

# The default branch is resolved at most once per hour of failures, and a success is kept as the local origin/HEAD,
# so a PreToolUse on every Bash call does not touch the network again
w=$(repo netmiss "$BASE_CFG"); g "$w" remote set-head origin -d 2>/dev/null; g "$w" remote set-url origin ssh://nohost.invalid/x.git
pre "$w" "$NET_ENV" ls >/dev/null
row 'origin unreachable: the first call tries origin once'        "$(net)" network
pre "$w" "$NET_ENV" ls >/dev/null
row 'origin unreachable: a second call makes no network call'     "$(net)" cached
w=$(repo netok "$BASE_CFG"); g "$w" remote set-head origin -d 2>/dev/null
pre "$w" ls >/dev/null; g "$w" remote set-url origin ssh://nohost.invalid/x.git
pre "$w" "$NET_ENV" ls >/dev/null
row 'origin answered once: later calls make no network call'      "$(net)" cached

# trunk default, a pushed non-default main with the branch's config, no origin/HEAD, origin unreachable: never main
w=$(B=trunk repo unreach "$BASE_CFG"); branch_cfg "$w" '{"command": "echo branch > ran", "paths": ["src"], "gate": []}'
g "$w" push -q origin feat:main && g "$w" fetch -q origin && g "$w" remote set-head origin -d 2>/dev/null; mv "$T/unreach/origin.git" "$T/unreach/moved.git"
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'origin unreachable, pushed main: main is not used (no run)'  "$(ran "$w")" none
row 'origin unreachable, pushed main: nothing recorded'           "$(recorded)" norecord

# GIT_DIR naming another repo (no origin) does not redirect the hook
w=$(repo gitdir "$BASE_CFG"); branch_cfg "$w" '{"command": "true", "paths": ["src"], "gate": []}'; git init -q "$T/gitdir/other"; echo b >> "$w/src/a"
row 'GIT_DIR naming another repo: the default branch still gates'  "$(pre "$w" "GIT_DIR=$T/gitdir/other/.git")" deny

# The config source and the comparison base are the same branch. The local origin/HEAD says main, but origin was never
# asked for it, so origin is asked once and its answer (trunk) supplies both
w=$(B=trunk repo stale "$BASE_CFG"); g "$w" checkout -qb m && printf '%s\n' '{"command": "echo main > ran", "paths": ["src"]}' > "$w/.claude/full-test.json" \
  && g "$w" commit -qam main && g "$w" push -q origin m:main && g "$w" fetch -q origin && g "$w" checkout -q feat || exit 1
g "$w" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main; rm -rf "$FULL_TEST_STATE_DIR"
out=$(cd "$w" && python3 "$H" run 2>/dev/null | sed -n 's/.*Recorded: \([^ ]*\).*/\1/p')
row 'config source and comparison base agree (both trunk)'         "$([ "$(ran "$w")" = base ] && [ "$out" = origin/trunk ] && echo same || echo "differ")" same

# a path with non-ASCII characters and a space
w=$(repo "日本語 dir/プロジェクト" "$BASE_CFG"); branch_cfg "$w" '{"command": "echo branch > ran", "paths": ["src"], "gate": []}'
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'non-ASCII path with a space: the default branch command runs' "$(ran "$w")" base

# origin's default moved from main to trunk and main was deleted; the clone's origin/HEAD still names the pruned
# origin/main. State A: origin is asked again (trunk). State B: someone pushed a new main; it must not be fetched by name
rot() {  # rot <name> <branch config> -> clone whose origin/HEAD dangles (origin default is now trunk)
  w=$(repo "$1" "$BASE_CFG"); [ -n "$2" ] && branch_cfg "$w" "$2"; o="$T/$1/origin.git"
  g "$w" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
  git -C "$o" branch trunk main && git -C "$o" symbolic-ref HEAD refs/heads/trunk && git -C "$o" branch -D -q main \
    && g "$w" fetch -q --prune origin || exit 1
  echo "$w"; }
w=$(rot dangleA ''); rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'dangling origin/HEAD, origin reachable: asks origin (trunk)'  "$(ran "$w")" base
w=$(rot dangleB '{"command": "echo branch > ran", "paths": ["src"], "gate": []}')
g "$w" push -q origin feat:x && git -C "$T/dangleB/origin.git" update-ref refs/heads/main refs/heads/x || exit 1
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'dangling origin/HEAD, pushed main: main is not fetched'        "$(ran "$w")" base
echo b >> "$w/src/a"
row 'dangling origin/HEAD, pushed main: release still gated'        "$(pre "$w")" deny

# origin renamed main to trunk and deleted main; the clone (checked before the rename) never prunes, so origin/HEAD still
# names origin/main. Someone pushes a main with a loosened config and the clone runs an ordinary fetch: trunk still rules
w=$(repo renamed "$BASE_CFG"); o="$T/renamed/origin.git"; g "$w" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
pre "$w" ls >/dev/null
git -C "$o" branch -m main trunk && git -C "$o" symbolic-ref HEAD refs/heads/trunk || exit 1
branch_cfg "$w" '{"command": "echo branch > ran", "paths": ["src"], "gate": []}'; g "$w" push -q origin feat:main && g "$w" fetch -q origin || exit 1
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'default renamed, pushed main fetched: run uses trunk command'  "$(ran "$w")" base

# A tag named origin/main (pushed to origin and fetched) does not hide a valid origin/HEAD, nor stand in for the comparison base
w=$(repo tagged "$BASE_CFG"); echo b >> "$w/src/a"; g "$w" commit -qam work; g "$w" push -q origin feat:refs/tags/origin/main
g "$w" fetch -q --tags origin; rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && python3 "$H" run >/dev/null 2>&1)
row 'tag named origin/main: a branch result is not recorded'          "$(recorded)" norecord
g "$w" remote set-url origin ssh://nohost.invalid/x.git; pre "$w" "$NET_ENV" ls >/dev/null
row 'tag named origin/main: a second call makes no network call'     "$(net)" cached

# origin exists but cannot be read: not opted in (the working tree config is not used)
w=$(repo unreadable "$BASE_CFG"); g "$w" remote set-url origin "$T/missing.git"; g "$w" update-ref -d refs/remotes/origin/main
row 'origin unreadable: not opted in (status)'                    "$(cd "$w" && python3 "$H" status 2>/dev/null | grep -q 'Not configured' && echo off || echo on)" off
# GIT_DIR naming another repo does not redirect the test command either (it runs against the repo it gates)
w=$(repo gdrun '{"command": "git log -1 --format=%s origin/main > ran", "paths": ["src"]}'); git init -q "$T/gdrun/other"
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$w" && GIT_DIR="$T/gdrun/other/.git" python3 "$H" run >/dev/null 2>&1)
row 'GIT_DIR naming another repo: the test command reads this repo' "$(ran "$w")" base

# partial clone (blob:none) with origin gone: the config blob cannot be fetched, and stderr says so (not a quiet "not opted in")
w=$(repo partial "$BASE_CFG"); git -C "$T/partial/origin.git" config uploadpack.allowFilter true
git clone -q --filter=blob:none --no-checkout "file://$T/partial/origin.git" "$T/partial/clone" 2>/dev/null && mv "$T/partial/origin.git" "$T/partial/gone.git" || exit 1
err=$(cd "$T/partial/clone" && python3 "$H" status 2>&1 >/dev/null)
row 'partial clone offline: a note that the config cannot be read'  "$(printf '%s' "$err" | grep -q 'cannot read' && echo note || echo quiet)" note
# partial clone with origin reachable: the config blob is fetched on demand and applies
w=$(repo partok "$BASE_CFG"); git -C "$T/partok/origin.git" config uploadpack.allowFilter true
git clone -q --filter=blob:none --no-checkout "file://$T/partok/origin.git" "$T/partok/clone" 2>/dev/null || exit 1
rm -rf "$FULL_TEST_STATE_DIR"; (cd "$T/partok/clone" && python3 "$H" run >/dev/null 2>&1)
row 'partial clone, origin reachable: run uses the default command' "$(ran "$T/partok/clone")" base
# partial clone with origin unreachable: a failed blob fetch is cached like a failed lookup, so the next call stays offline
w=$(repo partoff "$BASE_CFG"); git -C "$T/partoff/origin.git" config uploadpack.allowFilter true
git clone -q --filter=blob:none --no-checkout "file://$T/partoff/origin.git" "$T/partoff/clone" 2>/dev/null || exit 1
g "$T/partoff/clone" remote set-url origin ssh://nohost.invalid/x.git
pre "$T/partoff/clone" "$NET_ENV" ls >/dev/null
row 'partial clone, origin unreachable: the first call tries origin'  "$(net)" network
pre "$T/partoff/clone" "$NET_ENV" ls >/dev/null
row 'partial clone, origin unreachable: a second call stays offline' "$(net)" cached
exit $fail
