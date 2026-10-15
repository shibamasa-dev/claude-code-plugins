#!/bin/bash
# Live check of orchestrator-report.py: a session that writes to a PR or issue is told to report to the repo's
# orchestrator session (the one running session whose title starts with 🎯 in the same repository), and nobody else is.
# HOME and CLAUDE_PLUGIN_DATA point at a temp directory so real state is untouched. A fake `claude` prints canned
# `agents --json` output (same keys as the real one); a fake `gh` keeps everything off the network.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/orchestrator-report.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/orr.XXXX")
T=$(cd "$T" && pwd -P)
export HOME="$T" CLAUDE_PLUGIN_DATA="$T/data"
unset GH_REPO CLAUDE_CODE_REMOTE CLAUDE_CODE_PROJECTS_SESSION

mkdir -p "$T/bin"
printf '#!/bin/bash\n[ "$1 $2" = "agents --json" ] && cat "%s/agents.json"\n' "$T" > "$T/bin/claude"
printf '#!/bin/bash\nexit 0\n' > "$T/bin/gh"
chmod +x "$T/bin/claude" "$T/bin/gh"
export PATH="$T/bin:$PATH"

# A repo with a worktree, and an unrelated repo
g() { git -c user.name=t -c user.email=t@example.com "$@" >/dev/null 2>&1; }
g init -q "$T/repo" && g -C "$T/repo" commit -q --allow-empty -m init
g -C "$T/repo" remote add origin https://github.com/o/r.git
g -C "$T/repo" worktree add -q "$T/repo-wt" -b feat
g init -q "$T/other" && g -C "$T/other" remote add origin https://github.com/x/y.git

ORCH=3f2a9c1e-7b4d-4e8a-9c0f-1a2b3c4d5e6f
CHILD=8d7e6f5a-4b3c-4d2e-8f1a-0b9c8d7e6f5a
# agents <entries...>: each entry is "cwd|sessionId|name"
agents() {
  python3 - "$@" > "$T/agents.json" <<'PY'
import json, sys
out = []
for i, e in enumerate(sys.argv[1:]):
    cwd, sid, name = e.split("|", 2)
    out.append({"pid": 41000 + i, "cwd": cwd, "kind": "interactive", "startedAt": 1792050000000 + i,
                "sessionId": sid, "name": name, "status": "idle" if i else "busy"})
print(json.dumps(out, ensure_ascii=False))
PY
}

# post <session> <cwd> <tool_name> <tool_input(JSON)> <tool_response(JSON)> -> inject / none
post() {
  out=$(python3 - "$@" <<'PY' | python3 "$HOOK"
import json, sys
sid, cwd, tn, ti, tr = sys.argv[1:6]
print(json.dumps({"hook_event_name": "PostToolUse", "session_id": sid, "cwd": cwd,
                  "tool_name": tn, "tool_input": json.loads(ti), "tool_response": json.loads(tr)}))
PY
)
  case "$out" in *additionalContext*'🎯 r'*) echo inject ;; '') echo none ;; *) echo "other" ;; esac
}
j() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
bash_post() {  # bash_post <session> <cwd> <command> <stdout>
  post "$1" "$2" Bash "{\"command\":$(j "$3")}" "{\"stdout\":$(j "$4"),\"stderr\":\"\"}"
}
row() { printf '  %-62s -> %-6s (expect %s)\n' "$1" "$2" "$3"; }

PR_CREATE="gh pr create -R o/r --title t --body 'Refs: none (verbal request)'"
ISSUE_IN='{"method":"create","owner":"o","repo":"r","title":"t","body":"b"}'
ISSUE_OUT='[{"type":"text","text":"{\"html_url\":\"https://github.com/o/r/issues/12\",\"number\":12}"}]'

echo '=== A: who gets told to report ==='
agents "$T/repo|$ORCH|🎯 r" "$T/repo|$CHILD|ログイン画面の不具合を直す"
row 'another session in the repo runs gh pr create' \
  "$(bash_post s-a1 "$T/repo" "$PR_CREATE" 'https://github.com/o/r/pull/7')" inject
row 'another session in the repo creates an issue with the connector' \
  "$(post s-a2 "$T/repo" mcp__github__issue_write "$ISSUE_IN" "$ISSUE_OUT")" inject
row 'the orchestrator itself (same session id) writes' \
  "$(bash_post "$ORCH" "$T/repo" "$PR_CREATE" 'https://github.com/o/r/pull/8')" none
row 'a session in a worktree of the repo runs gh pr create' \
  "$(bash_post s-a4 "$T/repo-wt" "$PR_CREATE" 'https://github.com/o/r/pull/9')" inject

echo
echo '=== B: no single orchestrator for the repo ==='
agents "$T/other|$ORCH|🎯 other" "$T/repo|$CHILD|週次レポートの集計"
row 'the only 🎯 session is in another repo' \
  "$(bash_post s-b1 "$T/repo" "$PR_CREATE" 'https://github.com/o/r/pull/7')" none
agents "$T/repo|$ORCH|🎯 r" "$T/repo-wt|$CHILD|🎯 r (2)"
row 'two 🎯 sessions match the repo' \
  "$(bash_post s-b2 "$T/repo" "$PR_CREATE" 'https://github.com/o/r/pull/7')" none

echo
echo '=== C: skips ==='
agents "$T/repo|$ORCH|🎯 r" "$T/repo|$CHILD|ログイン画面の不具合を直す"
row 'cloud session (CLAUDE_CODE_REMOTE=true)' \
  "$(CLAUDE_CODE_REMOTE=true bash_post s-c1 "$T/repo" "$PR_CREATE" 'https://github.com/o/r/pull/7')" none
first=$(bash_post s-c2 "$T/repo" "gh pr edit 7 -R o/r --body x" 'https://github.com/o/r/pull/7')
second=$(bash_post s-c2 "$T/repo" "gh pr edit 7 -R o/r --title y" 'https://github.com/o/r/pull/7')
row 'same PR twice in one session: told the first time only' \
  "$([ "$first $second" = 'inject none' ] && echo ok || echo "bad")" ok
for i in 1 2 3 4 5 6; do
  bash_post s-c3 "$T/repo" "gh pr edit 7 -R o/r --title t$i" 'https://github.com/o/r/pull/7' > "$T/par.$i" &
done
wait
row 'same PR from 6 parallel tool calls: told exactly once' \
  "$([ "$(cat "$T"/par.* | grep -c '^inject$')" = 1 ] && echo ok || echo bad)" ok

echo
echo '=== D: the repository written to decides the orchestrator ==='
agents "$T/repo|$ORCH|🎯 r" "$T/repo|$CHILD|ログイン画面の不具合を直す"
row 'gh pr create -R x/y from this repo; x/y has no orchestrator' \
  "$(bash_post s-d1 "$T/repo" "gh pr create -R x/y --title t --body b" 'https://github.com/x/y/pull/3')" none
agents "$T/repo|$ORCH|🎯 r" "$T/other|$CHILD|🎯 xy"
out=$(python3 - "$T/repo" <<'PY2' | python3 "$HOOK"
import json, sys
print(json.dumps({"hook_event_name": "PostToolUse", "session_id": "s-d2", "cwd": sys.argv[1], "tool_name": "Bash",
                  "tool_input": {"command": "gh pr create -R x/y --title t --body b"},
                  "tool_response": {"stdout": "https://github.com/x/y/pull/3", "stderr": ""}}))
PY2
)
row 'gh pr create -R x/y from this repo: told to report to x/y orchestrator' \
  "$(printf '%s' "$out" | grep -q '🎯 xy' && ! printf '%s' "$out" | grep -q '🎯 r[^ ]' && echo ok || echo bad)" ok

rm -rf "$T"
