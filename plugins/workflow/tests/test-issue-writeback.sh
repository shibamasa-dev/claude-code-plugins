#!/bin/bash
# Live check of issue-writeback.py: PRs are not tracked, and an issue read but not written still stops at Stop as before.
# HOME points at a temp directory so the real ~/.claude is untouched (gh is only used in forms that don't hit the network).
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/issue-writeback.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/iwb.XXXX")
export HOME="$T"
# Fake gh: answers only `gh pr view` (resolving a PR not given by number). The PR of the current branch and of my-branch is o/r#455;
# any other selector (e.g. a file name taken by mistake) gets no answer
mkdir -p "$T/bin"
printf '#!/bin/bash\n[ "$1 $2" = "pr view" ] && case "$3" in -R|--json|my-branch) echo https://github.com/o/r/pull/455 ;; esac\n' > "$T/bin/gh"
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH"

# post <session> <tool_name> <tool_input(JSON)> <tool_response(JSON)>
post() {
  python3 - "$@" <<'PY' | python3 "$HOOK"
import json, sys
sid, tn, ti, tr = sys.argv[1:5]
print(json.dumps({"hook_event_name": "PostToolUse", "session_id": sid, "cwd": "/",
                  "tool_name": tn, "tool_input": json.loads(ti), "tool_response": json.loads(tr)}))
PY
}
bash_post() {  # bash_post <session> <command> <stdout>
  post "$1" Bash "$(python3 -c 'import json,sys; print(json.dumps({"command": sys.argv[1]}))' "$2")" \
    "$(python3 -c 'import json,sys; print(json.dumps({"stdout": sys.argv[1], "stderr": ""}))' "$3")"
}
# stops <session>: send Stop 3 times (K_STOPS); block if any of them blocked
stops() {
  r=allow
  for _ in 1 2 3; do
    out=$(printf '{"hook_event_name":"Stop","session_id":"%s"}' "$1" | python3 "$HOOK")
    case "$out" in *'"block"'*) r=block ;; esac
  done
  echo "$r"
}
row() { printf '  %-58s -> %-5s (expect %s)\n' "$1" "$2" "$3"; }

echo '=== A: PRs are not tracked ==='
bash_post a1 'gh api repos/o/r/issues/455/comments' '[{"html_url":"https://github.com/o/r/pull/455#issuecomment-1"}]'
row 'only read PR comments through the issues API' "$(stops a1)" 'allow'

post a2 mcp__github__issue_read '{"method":"get","owner":"o","repo":"r","issue_number":455}' \
  '{"html_url":"https://github.com/o/r/pull/455","title":"x"}'
row 'only read a PR with issue_read' "$(stops a2)" 'allow'

bash_post a3 'gh pr view 455 -R o/r' 'title: x'
bash_post a3 'gh pr edit 455 -R o/r --body-file /tmp/b.md' 'https://github.com/o/r/pull/455'
row 'gh pr view, then gh pr edit' "$(stops a3)" 'allow'

bash_post a4 'gh api repos/o/r/issues/455' '{"title":"x"}'
bash_post a4 'gh pr comment 455 -R o/r --body ok' 'https://github.com/o/r/pull/455#issuecomment-2'
row 'a read not known to be a PR is cleared by gh pr comment' "$(stops a4)" 'allow'

bash_post a5 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a5 'gh pr review --approve 455 -R o/r' ''
row 'cleared by gh pr review with the number after options' "$(stops a5)" 'allow'

bash_post a6 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a6 'gh pr review --approve -R o/r' ''
row 'cleared by gh pr review with no number (current branch)' "$(stops a6)" 'allow'

bash_post a7 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a7 'gh pr edit my-branch -R o/r --body x' ''
row 'cleared by gh pr edit naming a branch' "$(stops a7)" 'allow'

bash_post a8 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a8 "gh pr close -c 'done' 455 -R o/r" ''
row 'skips the value of close -c and picks up the number' "$(stops a8)" 'allow'

bash_post a9 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a9 'gh pr edit --attach ./image.png 455 -R o/r' ''
row 'skips the value of edit --attach and picks up the number' "$(stops a9)" 'allow'

bash_post a10 'gh api repos/o/r/issues/77 --jq .title' 'x'
bash_post a10 'gh pr review 77 --repo=o/r --approve' ''
row 'the --repo=o/r form resolves the right repo' "$(stops a10)" 'allow'

echo
echo '=== B: issues work as before ==='
bash_post b1 'gh issue view 12 -R o/r' 'title: x'
row 'read with gh issue view and not updated' "$(stops b1)" 'block'

post b2 mcp__github__issue_read '{"method":"get","owner":"o","repo":"r","issue_number":12}' \
  '{"html_url":"https://github.com/o/r/issues/12","body":"Related: https://github.com/o/r/pull/120"}'
row 'read an issue whose body links a PR with another number, not updated' "$(stops b2)" 'block'

bash_post b3 'gh issue view 12 -R o/r' 'title: x'
bash_post b3 'gh issue comment 12 -R o/r --body ok' 'https://github.com/o/r/issues/12#issuecomment-3'
row 'gh issue view, then gh issue comment' "$(stops b3)" 'allow'

bash_post b4 'gh issue view 12 -R o/r' 'title: x'
bash_post b4 'gh pr comment -R o/r --body 12' ''
row 'a number in the gh pr comment body is not taken as the PR number' "$(stops b4)" 'block'

# The Stop message prints a runnable dismiss command (python3 "<path to the hook>" dismiss ...); running it as printed clears the issue
bash_post b5 'gh issue view 12 -R o/r' 'title: x'
for _ in 1 2; do printf '{"hook_event_name":"Stop","session_id":"b5"}' | python3 "$HOOK" >/dev/null; done
cmd=$(printf '{"hook_event_name":"Stop","session_id":"b5"}' | python3 "$HOOK" \
      | python3 -c 'import json,sys; print([l.strip() for l in json.load(sys.stdin)["reason"].splitlines() if " dismiss " in l][0])')
row 'the printed dismiss command names the hook script' "$([[ "$cmd" == "python3 \"$HOOK\" dismiss o/r#12 --session b5 "* ]] && echo ok || echo bad)" 'ok'
sh -c "${cmd/<reason>/test: nothing decided}" >/dev/null
row 'running the printed dismiss command clears the block' "$(stops b5)" 'allow'

rm -rf "$T"
