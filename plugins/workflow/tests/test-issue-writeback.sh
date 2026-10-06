#!/bin/bash
# issue-writeback.py の実測。PR は追わず、issue は従来どおり読んだまま終えると Stop で止まるか。
# 本物の ~/.claude を触らないよう HOME を一時ディレクトリに向ける（gh はネットワークに出ない形だけ使う）。
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/issue-writeback.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/iwb.XXXX")
export HOME="$T"
# 偽の gh: `gh pr view`（番号で指していない PR の解決）だけに答える。今のブランチと my-branch の PR を o/r#455 とし、
# それ以外の指定（ファイル名を取り違えた等）には答えない
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

bash_post a5 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a5 'gh pr review --approve 455 -R o/r' ''
row 'オプションの後ろに番号がある gh pr review でも解消' "$(stops a5)" 'allow'

bash_post a6 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a6 'gh pr review --approve -R o/r' ''
row '番号なし（今のブランチ）の gh pr review でも解消' "$(stops a6)" 'allow'

bash_post a7 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a7 'gh pr edit my-branch -R o/r --body x' ''
row 'ブランチ名で指した gh pr edit でも解消' "$(stops a7)" 'allow'

bash_post a8 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a8 "gh pr close -c 'done' 455 -R o/r" ''
row 'close の -c の値を飛ばして番号を拾う' "$(stops a8)" 'allow'

bash_post a9 'gh api repos/o/r/issues/455 --jq .title' 'x'
bash_post a9 'gh pr edit --attach ./image.png 455 -R o/r' ''
row 'edit の --attach の値を飛ばして番号を拾う' "$(stops a9)" 'allow'

bash_post a10 'gh api repos/o/r/issues/77 --jq .title' 'x'
bash_post a10 'gh pr review 77 --repo=o/r --approve' ''
row '--repo=o/r の形でもリポを取り違えない' "$(stops a10)" 'allow'

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

bash_post b4 'gh issue view 12 -R o/r' 'title: x'
bash_post b4 'gh pr comment -R o/r --body 12' ''
row 'gh pr comment の本文の数字を PR 番号と取り違えない' "$(stops b4)" 'block'

rm -rf "$T"
