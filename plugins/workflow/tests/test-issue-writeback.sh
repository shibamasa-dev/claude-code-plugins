#!/bin/bash
# issue-writeback.py の実測。PR は追わず、issue は従来どおり読んだまま終えると Stop で止まるか。
# 本物の ~/.claude を触らないよう HOME を一時ディレクトリに向ける（gh はネットワークに出ない形だけ使う）。
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/issue-writeback.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/iwb.XXXX")
export HOME="$T"

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
# stops <session>: Stop を 3 回（K_STOPS）送り、一度でも block されたら block
stops() {
  r=allow
  for _ in 1 2 3; do
    out=$(printf '{"hook_event_name":"Stop","session_id":"%s"}' "$1" | python3 "$HOOK")
    case "$out" in *'"block"'*) r=block ;; esac
  done
  echo "$r"
}
row() { printf '  %-58s -> %-5s (%s 期待)\n' "$1" "$2" "$3"; }

echo '=== A: PR は追わない ==='
bash_post a1 'gh api repos/o/r/issues/455/comments' '[{"html_url":"https://github.com/o/r/pull/455#issuecomment-1"}]'
row 'issues API で PR のコメントを読んだだけ' "$(stops a1)" 'allow'

post a2 mcp__github__issue_read '{"method":"get","owner":"o","repo":"r","issue_number":455}' \
  '{"html_url":"https://github.com/o/r/pull/455","title":"x"}'
row 'issue_read で PR を読んだだけ' "$(stops a2)" 'allow'

bash_post a3 'gh pr view 455 -R o/r' 'title: x'
bash_post a3 'gh pr edit 455 -R o/r --body-file /tmp/b.md' 'https://github.com/o/r/pull/455'
row 'gh pr view のあと gh pr edit' "$(stops a3)" 'allow'

bash_post a4 'gh api repos/o/r/issues/455' '{"title":"x"}'
bash_post a4 'gh pr comment 455 -R o/r --body ok' 'https://github.com/o/r/pull/455#issuecomment-2'
row 'PR と分からず読んだ記録も gh pr comment で解消' "$(stops a4)" 'allow'

echo
echo '=== B: issue は従来どおり ==='
bash_post b1 'gh issue view 12 -R o/r' 'title: x'
row 'gh issue view で読んで更新しない' "$(stops b1)" 'block'

post b2 mcp__github__issue_read '{"method":"get","owner":"o","repo":"r","issue_number":12}' \
  '{"html_url":"https://github.com/o/r/issues/12","body":"関連: https://github.com/o/r/pull/120"}'
row '本文に別番号の PR リンクがある issue を読んで更新しない' "$(stops b2)" 'block'

bash_post b3 'gh issue view 12 -R o/r' 'title: x'
bash_post b3 'gh issue comment 12 -R o/r --body ok' 'https://github.com/o/r/issues/12#issuecomment-3'
row 'gh issue view のあと gh issue comment' "$(stops b3)" 'allow'

rm -rf "$T"
