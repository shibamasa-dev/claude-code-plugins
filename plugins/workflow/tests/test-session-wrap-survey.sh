#!/bin/bash
# Live check of skills/session-wrap/scripts/survey.py: the flags it raises for a repo with leftovers and for one without.
# Each case is a throwaway clone of a local bare remote; the leftover is made for real (an edit, a commit that is not
# pushed, a read recorded by the real issue-writeback hook). HOME and CLAUDE_PLUGIN_DATA point at a temp directory, so
# the real ~/.claude is untouched and no network is used.
# Synthesized: `claude agents --json` answers [] (the session is passed with --session, so survey.py uses the cwd), and
# `gh pr view` is a fake that answers "no PR" except in the PR case, where it prints an OPEN PR in the shape of
# `gh pr view --json number,url,state,reviewDecision,isDraft`.
# Expected flags come from SKILL.md step 3 (DIRTY / UNPUSHED / PR_OPEN / PENDING_ISSUE); that an untracked file alone
# raises DIRTY comes from survey.py's docstring, not the skill.
set -u
D="$(cd "$(dirname "$0")/.." && pwd)"
SV="$D/skills/session-wrap/scripts/survey.py"; IW="$D/hooks/issue-writeback.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/survey.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_PLUGIN_DATA="$T/data/workflow-test"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
export GIT_CONFIG_NOSYSTEM=1
mkdir -p "$HOME" "$T/bin"
printf '#!/bin/bash\necho "[]"\n' > "$T/bin/claude"
# Fake gh: `gh pr view` finds a PR only when $T/pr.json exists
printf '#!/bin/bash\n[ "$1 $2" = "pr view" ] && [ -f "%s/pr.json" ] && cat "%s/pr.json" && exit 0\nexit 1\n' "$T" "$T" > "$T/bin/gh"
chmod +x "$T/bin/claude" "$T/bin/gh"
export PATH="$T/bin:$PATH"
row() { printf '  %-58s -> %-5s (expect %s)\n' "$1" "$2" "$3"; }

git init -q --bare "$T/remote.git"
git -C "$T/remote.git" symbolic-ref HEAD refs/heads/main   # so clones check out main whatever init.defaultBranch says
git clone -q "$T/remote.git" "$T/seed" 2>/dev/null
(cd "$T/seed" && git checkout -q -b main && echo a > a.txt && git add a.txt && git commit -qm init && git push -q -u origin main) \
  || { echo 'setup: could not push the seed commit'; exit 1; }
# repo <name> [branch]: a fresh clone of main with everything pushed; on a new <branch> (pushed, with upstream) when given
repo() {
  R="$T/$1"; git clone -q "$T/remote.git" "$R" 2>/dev/null
  [ "$(git -C "$R" rev-parse --abbrev-ref HEAD 2>/dev/null)" = main ] || { echo "setup: clone $1 is not on main"; exit 1; }
  if [ "${2:-}" ]; then
    (cd "$R" && git checkout -q -b "$2" && git push -q -u origin "$2" 2>/dev/null) || { echo "setup: push $2 failed"; exit 1; }
  fi
}
# flags <session>: the flags survey.py --json reports for the repo in $R, space-separated ("none" when empty)
flags() {
  (cd "$R" && python3 "$SV" --session "$1" --json 2>/dev/null) \
    | python3 -c 'import json,sys; f=json.load(sys.stdin)["flags"]; print(" ".join(f) or "none")'
}
# hook_bash <session> <command>: a PostToolUse of Bash through the real issue-writeback hook, cwd = $R
hook_bash() {
  python3 - "$1" "$2" "$R" <<'PY' | python3 "$IW"
import json, sys
sid, cmd, cwd = sys.argv[1:4]
print(json.dumps({"hook_event_name": "PostToolUse", "session_id": sid, "cwd": cwd, "tool_name": "Bash",
                  "tool_input": {"command": cmd}, "tool_response": {"stdout": "title: x", "stderr": ""}}))
PY
}
is() { [ "$1" = "$2" ] && echo ok || echo "bad: $1"; }

echo '=== without leftovers ==='
repo clean
row 'everything committed and pushed, no issue read' "$(is "$(flags s-clean)" none)" ok
repo clean-feat feat-clean
row 'same on a pushed working branch with no PR' "$(is "$(flags s-clean-feat)" none)" ok
repo written
hook_bash s-written 'gh issue view 12 -R o/r'
hook_bash s-written 'gh issue comment 12 -R o/r --body done'
row 'an issue read and then commented on' "$(is "$(flags s-written)" none)" ok

echo
echo '=== with leftovers ==='
repo dirty
echo b >> "$R/a.txt"
row 'an edit to a tracked file -> DIRTY' "$(is "$(flags s-dirty)" DIRTY)" ok
repo untracked
echo n > "$R/new.txt"
row 'a new untracked file -> DIRTY' "$(is "$(flags s-untracked)" DIRTY)" ok
repo unpushed feat-unpushed
(cd "$R" && echo c > c.txt && git add c.txt && git commit -qm local)
row 'a commit not pushed to the upstream -> UNPUSHED' "$(is "$(flags s-unpushed)" UNPUSHED)" ok
repo pending
hook_bash s-pending 'gh issue view 12 -R o/r'
row 'an issue read and not written back -> PENDING_ISSUE' "$(is "$(flags s-pending)" PENDING_ISSUE)" ok
row '  ...naming the issue' "$(is "$(cd "$R" && python3 "$SV" --session s-pending 2>/dev/null | grep -o 'o/r#12')" 'o/r#12')" ok
repo pr feat-pr
printf '{"number":7,"url":"https://github.com/o/r/pull/7","state":"OPEN","reviewDecision":"","isDraft":false}\n' > "$T/pr.json"
row 'an open PR for the working branch -> PR_OPEN' "$(is "$(flags s-pr)" PR_OPEN)" ok
rm -f "$T/pr.json"
