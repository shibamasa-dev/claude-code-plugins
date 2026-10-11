#!/bin/bash
# Live check of dev_flow_gate.py. Each of the three stop points (PR body markers, forgetting to wait, merging without `## Result`)
# is checked as a "stops / passes" pair, through both the connector and gh.
# CLAUDE_PLUGIN_DATA points at a temp directory so real state is untouched (no network access).
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/dev_flow_gate.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/dfg.XXXX")
export CLAUDE_PLUGIN_DATA="$T/data" HOME="$T"
unset GH_REPO
cd "$T" || exit 1

# ev <event> <session> <tool_name> <tool_input(JSON)> [tool_response(JSON)] -> the hook's output
ev() {
  python3 - "$@" <<'PY' | python3 "$HOOK"
import json, sys
a = sys.argv[1:] + ["null"] * 5
e, sid, tn, ti, tr = a[:5]
d = {"hook_event_name": e, "session_id": sid, "cwd": ".", "tool_name": tn,
     "tool_input": json.loads(ti) if ti != "null" else {}}
if e == "PostToolUse":
    d["tool_response"] = json.loads(tr)
print(json.dumps(d))
PY
}
j() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }   # string to JSON
bash_in() { printf '{"command":%s}' "$(j "$1")"; }
bash_out() { printf '{"stdout":%s,"stderr":""}' "$(j "$1")"; }

pre() { case "$(ev PreToolUse "$@")" in *'"deny"'*) echo deny ;; *) echo allow ;; esac; }
post() { case "$(ev PostToolUse "$@")" in *additionalContext*) echo inject ;; *) echo none ;; esac; }
stop() {  # stop <session> [active]
  out=$(printf '{"hook_event_name":"Stop","session_id":"%s","stop_hook_active":%s}' "$1" "${2:-false}" | python3 "$HOOK")
  case "$out" in *'"block"'*) echo block ;; *) echo allow ;; esac
}
row() { printf '  %-60s -> %-6s (expect %s)\n' "$1" "$2" "$3"; }

CREATE=mcp__github__create_pull_request
MERGE=mcp__github__merge_pull_request
AUTO=mcp__github__enable_pr_auto_merge
OK_BODY=$'## Summary\nx\n\nCloses #5\nArch-Review: not-needed — wording fix only'
pr_in() { printf '{"owner":"O","repo":"R","title":"t","head":"%s","base":"main","body":%s}' "${2:-feat}" "$(j "$1")"; }
# Shape of a connector result ([{"type":"text","text":"<JSON>"}]). macOS bash 3.2 misreads nested "$(... \" ...)", so build it in python
pr_out() { python3 -c 'import json,sys; n=int(sys.argv[1]); print(json.dumps([{"type":"text","text":json.dumps({"html_url":"https://github.com/O/R/pull/%d" % n,"number":n})}]))' "$1"; }

echo '=== A: PR body markers (PreToolUse) ==='
row 'connector: both markers present' "$(pre a $CREATE "$(pr_in "$OK_BODY")")" allow
row 'connector: both markers missing' "$(pre a $CREATE "$(pr_in $'body only')")" deny
row 'connector: Closes only (no Arch-Review)' "$(pre a $CREATE "$(pr_in $'Closes #5')")" deny
row 'connector: Arch-Review only (no Closes/Refs)' "$(pre a $CREATE "$(pr_in $'Arch-Review: approved — https://example.com/go')")" deny
row 'connector: Refs: none (verbal request) + Arch-Review' "$(pre a $CREATE "$(pr_in $'Refs: none (verbal request)\nArch-Review: not-needed - typo')")" allow
row 'connector: Refs owner/repo#N in another repo' "$(pre a $CREATE "$(pr_in $'Refs other/repo#12\nArch-Review: approved -- GO in #12')")" allow
row 'connector: empty Arch-Review reason' "$(pre a $CREATE "$(pr_in $'Closes #5\nArch-Review: not-needed — ')")" deny
row 'connector: empty Arch-Review reason, more lines follow' "$(pre a $CREATE "$(pr_in $'Closes #5\nArch-Review: not-needed — \n\n## Summary')")" deny
row 'connector: markers only inside an HTML comment (template help)' "$(pre a $CREATE "$(pr_in $'<!-- Closes #5\nArch-Review: not-needed — x -->')")" deny
row 'connector: no body' "$(pre a $CREATE '{"owner":"O","repo":"R","title":"t","head":"f","base":"main"}')" deny
row 'gh: --body has both markers' "$(pre a Bash "$(bash_in "gh pr create -R O/R --title t --body '$OK_BODY'")")" allow
row 'gh: --body lacks markers' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -b 'x'")")" deny
printf '%s\n' "$OK_BODY" > body-ok.md; printf 'x\n' > body-ng.md
row 'gh: --body-file has markers' "$(pre a Bash "$(bash_in 'gh pr create -R O/R -t t --body-file body-ok.md')")" allow
row 'gh: --body-file lacks markers' "$(pre a Bash "$(bash_in 'cd . && gh pr create -R O/R -t t -F body-ng.md')")" deny
row 'gh: markers in --body via $(cat <<EOF ...)' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t --body \"\$(cat <<'EOF'
$OK_BODY
EOF
)\"")")" allow
row 'gh: markers in a -F - <<EOF heredoc' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -F - <<'EOF'
$OK_BODY
EOF")")" allow
row "gh: a heredoc with ' and # is still read" "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -F - <<'EOF'
## Summary
don't panic
$OK_BODY
EOF")")" allow
row 'gh: no markers in a -F - <<EOF heredoc' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -F - <<'EOF'
x
EOF")")" deny
row 'gh: --body "$BODY" (a variable; contents unknown)' "$(pre a Bash "$(bash_in 'gh pr create -R O/R -t t --body "$BODY"')")" deny
row 'gh: gh pr create --fill through env' "$(pre a Bash "$(bash_in 'env GH_REPO=O/R gh pr create --fill')")" deny
row 'gh: markers only in a different heredoc' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -F - <<'A'
x
A
cat <<'B'
$OK_BODY
B")")" deny
row 'gh: piped stdin (cat f | gh pr create -F -)' "$(pre a Bash "$(bash_in 'cat body-ok.md | gh pr create -R O/R -t t -F -')")" deny
row 'gh: gh pr create --fill after a newline' "$(pre a Bash "$(bash_in $'git push -u origin feat\ngh pr create --fill')")" deny
row 'gh: --fill (body cannot be checked)' "$(pre a Bash "$(bash_in 'gh pr create --fill')")" deny
row 'not gh (gh pr create inside echo)' "$(pre a Bash "$(bash_in "echo 'gh pr create --fill'")")" allow
row 'gh pr view is out of scope' "$(pre a Bash "$(bash_in 'gh pr view 3 -R O/R')")" allow

echo
echo '=== B: forgetting to wait (Stop) ==='
row 'session that created no PR' "$(stop b0)" allow
row 'creating a PR via connector tells the next step' "$(post b1 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 7)")" inject
row 'create a PR and end without waiting (1st time)' "$(stop b1)" block
row 'not stopped a 2nd time for the same PR' "$(stop b1)" allow
post b2 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 8)" >/dev/null
post b2 mcp__claude-code-remote__subscribe_pr_activity '{"repo":"O/R","pr_number":8}' '"ok"' >/dev/null
row 'subscribe to PR events, then end' "$(stop b2)" allow
post b3 Bash "$(bash_in "gh pr create -R O/R -t t -b '$OK_BODY'")" "$(bash_out 'https://github.com/O/R/pull/9')" >/dev/null
post b3 Monitor '{"command":"gh pr checks 9 --watch"}' '"started"' >/dev/null
row 'create a PR with gh, start a Monitor, then end' "$(stop b3)" allow
post b4 Bash "$(bash_in "gh pr create -R O/R -t t -b '$OK_BODY'")" "$(bash_out 'https://github.com/O/R/pull/10')" >/dev/null
row 'create a PR with gh and end without waiting' "$(stop b4)" block
post b5 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 11)" >/dev/null
row 'not stopped when stop_hook_active' "$(stop b5 true)" allow
post b7 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 12)" >/dev/null
post b7 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 13)" >/dev/null
post b7 mcp__claude-code-remote__subscribe_pr_activity '{"owner":"O","repo":"R","pullNumber":12}' '"ok"' >/dev/null
row 'two PRs, one subscribed: stops for the other' "$(stop b7)" block
post b8 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 14)" >/dev/null
post b8 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 15)" >/dev/null
post b8 Monitor '{"command":"API=https://api.github.com/repos/O/R\nfor pr in 14 15; do get $API/pulls/$pr/reviews; done"}' '"started"' >/dev/null
row 'not stopped if the Monitor command has both numbers' "$(stop b8)" allow
post b9 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 16)" >/dev/null
post b9 Monitor '{"command":"API=https://api.github.com/repos/other/x\nfor pr in 16; do :; done"}' '"started"' >/dev/null
row 'a Monitor watching another repo does not count' "$(stop b9)" block
post b10 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 30)" >/dev/null
post b10 Monitor '{"command":"sleep 30; echo done"}' '"started"' >/dev/null
row 'a number not written as a PR (sleep 30) does not count' "$(stop b10)" block
post b11 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 18)" >/dev/null
post b11 Bash "$(bash_in "gh pr create -R other/x -t t -b '$OK_BODY'")" "$(bash_out 'https://github.com/other/x/pull/18')" >/dev/null
post b11 Monitor '{"command":"gh pr checks 18 --watch"}' '"started"' >/dev/null
row 'same PR number in two repos, Monitor names no repo' "$(stop b11)" block
post b6 Bash "$(bash_in "gh pr create -R O/R -t t -b '$OK_BODY'")" '{"stdout":"","stderr":"GraphQL: was submitted too quickly"}' >/dev/null
row 'a failed gh pr create is not recorded' "$(stop b6)" allow

echo
echo '=== C: merging without `## Result` (PreToolUse) ==='
mk() { post "$1" $CREATE "$(pr_in "$2" "${4:-feat}")" "$(pr_out "$3")" >/dev/null; }
iw_out() { python3 -c 'import json,sys; o,r,n=sys.argv[1:4]; print(json.dumps([{"type":"text","text":json.dumps({"html_url":"https://github.com/%s/%s/issues/%s" % (o,r,n)})}]))' "$@"; }
mi() { printf '{"owner":"%s","repo":"R","pullNumber":%s}' "${2:-O}" "$1"; }
mk c1 "$OK_BODY" 20
row 'no `## Result` record for the Closes issue (connector)' "$(pre c1 $MERGE "$(mi 20)")" deny
row 'same (enable_pr_auto_merge)' "$(pre c1 $AUTO "$(mi 20)")" deny
row 'same (gh pr merge <number> -R)' "$(pre c1 Bash "$(bash_in 'gh pr merge 20 -R O/R --squash')")" deny
row 'same (gh pr merge <URL>)' "$(pre c1 Bash "$(bash_in 'gh pr merge https://github.com/O/R/pull/20')")" deny
post c1 mcp__github__issue_write '{"method":"update","owner":"o","repo":"r","issue_number":5,"body":"Body\n\n## Result\n- done"}' "$(iw_out o r 5)" >/dev/null
row 'after writing `## Result` with issue_write (owner case ignored)' "$(pre c1 $MERGE "$(mi 20 o)")" allow
mk c2 "$OK_BODY" 21
post c2 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"Result pending"}' "$(iw_out O R 5)" >/dev/null
post c2 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"##\nResult"}' "$(iw_out O R 5)" >/dev/null
row '`##` and `Result` on separate lines is not a heading' "$(pre c2 $MERGE "$(mi 21)")" deny
row 'an update with no `## Result` in the body does not pass' "$(pre c2 $MERGE "$(mi 21)")" deny
post c2 mcp__github__issue_read '{"method":"get","owner":"O","repo":"R","issue_number":5}' "$(printf '[{"type":"text","text":%s}]' "$(j '{"body":"x\n\n## Result\nok"}')")" >/dev/null
row 'after reading and confirming `## Result` with issue_read' "$(pre c2 $MERGE "$(mi 21)")" allow
mk c3 "$OK_BODY" 22
row 'does not pass if the issue_read body has no `## Result`' "$(post c3 mcp__github__issue_read '{"method":"get","owner":"O","repo":"R","issue_number":5}' '{"body":"x"}' >/dev/null; pre c3 $MERGE "$(mi 22)")" deny
post c3 Bash "$(bash_in 'gh issue edit 5 -R O/R --body-file r.md')" "$(bash_out '')" >/dev/null
row 'not recorded if the gh issue edit body-file is unreadable' "$(pre c3 $MERGE "$(mi 22)")" deny
printf 'x\n\n## Result\n- done\n' > r.md
post c3 Bash "$(bash_in 'gh issue edit 5 -R O/R --body-file r.md')" "$(bash_out 'https://github.com/O/R/issues/5')" >/dev/null
row 'after writing `## Result` with gh issue edit (gh pr merge)' "$(pre c3 Bash "$(bash_in 'gh pr merge 22 -R O/R')")" allow
mk c4 "$OK_BODY" 23
post c4 Bash "$(bash_in 'gh issue view 5 -R O/R')" "$(bash_out $'title: x\n--\nbody\n\n## Result\nok')" >/dev/null
row 'after confirming with gh issue view (gh pr merge by branch name)' "$(pre c4 Bash "$(bash_in 'gh pr merge feat -R O/R')")" allow
mk c5 $'Refs #5\nArch-Review: not-needed — x' 24
row 'a PR with only Refs is not stopped' "$(pre c5 $MERGE "$(mi 24)")" allow
row 'a PR not created in this session is not stopped' "$(pre c5 $MERGE "$(mi 99)")" allow
row 'reminder after merging a PR not created here' "$(post c5 $MERGE "$(mi 99)" '"merged"')" inject
row 'nothing after merging a PR created here' "$(post c5 $MERGE "$(mi 24)" '"merged"')" none
mk c6 $'Fixes other/x#3, closes #6\nArch-Review: approved — #6' 25
post c6 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":6,"body":"## Result\nok"}' "$(iw_out O R 6)" >/dev/null
row 'two Closes, the one in another repo not written' "$(pre c6 $MERGE "$(mi 25)")" deny
post c6 mcp__github__issue_write '{"method":"update","owner":"other","repo":"x","issue_number":3,"body":"## Results\nok"}' "$(iw_out other x 3)" >/dev/null
row 'after writing both' "$(pre c6 $MERGE "$(mi 25)")" allow
row 'another session has separate records' "$(pre c1x $MERGE "$(mi 20)")" allow
mk c7 "$OK_BODY" 26
post c7 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"## Result\nok"}' '"interactive form has been shown to the user"' >/dev/null
row 'not recorded if issue_write only showed an approval form' "$(pre c7 $MERGE "$(mi 26)")" deny
row 'through a wrapper (env GH_REPO=O/R gh pr merge)' "$(pre c7 Bash "$(bash_in 'env GH_REPO=O/R gh pr merge 26')")" deny
row 'through a wrapper (command gh pr merge)' "$(pre c7 Bash "$(bash_in 'command gh pr merge 26 -R O/R')")" deny
row 'through a wrapper (timeout -s KILL 30 gh pr merge)' "$(pre c7 Bash "$(bash_in 'timeout -s KILL 30 gh pr merge 26 -R O/R')")" deny
row 'GH_REPO exported on an earlier line' "$(pre c7 Bash "$(bash_in 'export GH_REPO=O/R; gh pr merge 26 --squash')")" deny
row "inside bash -c '...'" "$(pre c7 Bash "$(bash_in "bash -c 'gh pr merge 26 -R O/R'")")" deny
row 'inside ( ... )' "$(pre c7 Bash "$(bash_in '(cd . && gh pr merge 26 -R O/R)')")" deny
row 'gh pr merge continued with a trailing \\' "$(pre c7 Bash "$(bash_in $'gh pr merge 26 \\\n  -R O/R')")" deny
row 'gh pr merge after a newline' "$(pre c7 Bash "$(bash_in $'git fetch\ngh pr merge 26 -R O/R')")" deny
row 'command -v gh does not run gh' "$(pre c7 Bash "$(bash_in 'command -v gh && echo ok')")" allow

mk c8 "$OK_BODY" 27
for d in or:O/R ox:other/x; do
  git init -q "repo-${d%%:*}" && git -C "repo-${d%%:*}" remote add origin "https://github.com/${d#*:}.git"
done
row 'resolved in the cd target repo (same number in another repo not stopped)' "$(pre c8 Bash "$(bash_in 'cd repo-ox && gh pr merge 27 --squash')")" allow
row 'resolved in the cd target repo (the repo of the created PR)' "$(pre c8 Bash "$(bash_in 'cd repo-or && gh pr merge 27 --squash')")" deny
row 'resolved with the inherited GH_REPO' "$(GH_REPO=other/x pre c8 Bash "$(bash_in 'gh pr merge 27')")" allow
post c8 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"x\n<!--\n## Result\n-->"}' "$(iw_out O R 5)" >/dev/null
post c8 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"x\n```md\n## Result\n```"}' "$(iw_out O R 5)" >/dev/null
row '`## Result` inside an HTML comment or code block does not count' "$(pre c8 $MERGE "$(mi 27)")" deny
# Older issues use the Japanese headings (`## 結果` / `## 次回への引き継ぎ`); they must stay accepted
mk c9 "$OK_BODY" 28
post c9 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"x\n\n## 結果\n- 済み"}' "$(iw_out O R 5)" >/dev/null
row 'legacy Japanese heading `## 結果` is still accepted' "$(pre c9 $MERGE "$(mi 28)")" allow
mk c10 "$OK_BODY" 29
post c10 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"x\n\n## Notes for next time\n- y"}' "$(iw_out O R 5)" >/dev/null
row '`## Notes for next time` is accepted' "$(pre c10 $MERGE "$(mi 29)")" allow

echo
echo '=== D: cleanup (SessionStart) ==='
# touch -d is GNU-only (macOS touch lacks it), so set the mtime back with python
python3 -c 'import os,sys,time; t=time.time()-40*86400; os.utime(sys.argv[1],(t,t))' "$CLAUDE_PLUGIN_DATA/dev-flow-gate/c1.json"
printf '{"hook_event_name":"SessionStart","session_id":"s"}' | python3 "$HOOK"
[ -e "$CLAUDE_PLUGIN_DATA/dev-flow-gate/c1.json" ] && r=kept || r=gone
row 'state files older than 30 days are removed' "$r" gone
[ -e "$CLAUDE_PLUGIN_DATA/dev-flow-gate/c2.json" ] && r=kept || r=gone
row 'newer state files are kept' "$r" kept

echo
echo '=== E: broken input does not crash ==='
out=$(printf 'not json' | python3 "$HOOK"; echo "rc=$?")
row 'broken JSON' "$( [ "$out" = 'rc=0' ] && echo quiet || echo noisy)" quiet

rm -rf "$T"
