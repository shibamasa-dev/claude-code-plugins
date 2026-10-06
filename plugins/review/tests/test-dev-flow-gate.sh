#!/bin/bash
# dev_flow_gate.py の実測。止める 3 か所（PR 本文の印・待ち忘れ・`## 結果` 無しのマージ）を、
# コネクタと gh の両方で「止まる／通る」の組にして確かめる。
# 本物の状態を触らないよう CLAUDE_PLUGIN_DATA を一時ディレクトリに向ける（ネットワークには出ない）。
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/dev_flow_gate.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/dfg.XXXX")
export CLAUDE_PLUGIN_DATA="$T/data" HOME="$T"
unset GH_REPO
cd "$T" || exit 1

# ev <event> <session> <tool_name> <tool_input(JSON)> [tool_response(JSON)] → フックの出力
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
j() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }   # 文字列を JSON に
bash_in() { printf '{"command":%s}' "$(j "$1")"; }
bash_out() { printf '{"stdout":%s,"stderr":""}' "$(j "$1")"; }

pre() { case "$(ev PreToolUse "$@")" in *'"deny"'*) echo deny ;; *) echo allow ;; esac; }
post() { case "$(ev PostToolUse "$@")" in *additionalContext*) echo inject ;; *) echo none ;; esac; }
stop() {  # stop <session> [active]
  out=$(printf '{"hook_event_name":"Stop","session_id":"%s","stop_hook_active":%s}' "$1" "${2:-false}" | python3 "$HOOK")
  case "$out" in *'"block"'*) echo block ;; *) echo allow ;; esac
}
row() { printf '  %-60s -> %-6s (%s 期待)\n' "$1" "$2" "$3"; }

CREATE=mcp__github__create_pull_request
MERGE=mcp__github__merge_pull_request
AUTO=mcp__github__enable_pr_auto_merge
OK_BODY=$'## 概要\nx\n\nCloses #5\nArch-Review: not-needed — 文言の修正だけ'
pr_in() { printf '{"owner":"O","repo":"R","title":"t","head":"%s","base":"main","body":%s}' "${2:-feat}" "$(j "$1")"; }
pr_out() { printf '[{"type":"text","text":%s}]' "$(j "{\"html_url\":\"https://github.com/O/R/pull/$1\",\"number\":$1}")"; }

echo '=== A: PR 本文の印（PreToolUse） ==='
row 'コネクタ: 印が両方ある' "$(pre a $CREATE "$(pr_in "$OK_BODY")")" allow
row 'コネクタ: 印が両方無い' "$(pre a $CREATE "$(pr_in $'本文だけ')")" deny
row 'コネクタ: Closes だけ（Arch-Review 無し）' "$(pre a $CREATE "$(pr_in $'Closes #5')")" deny
row 'コネクタ: Arch-Review だけ（Closes/Refs 無し）' "$(pre a $CREATE "$(pr_in $'Arch-Review: approved — https://example.com/go')")" deny
row 'コネクタ: Refs: none (verbal request) + Arch-Review' "$(pre a $CREATE "$(pr_in $'Refs: none (verbal request)\nArch-Review: not-needed - typo')")" allow
row 'コネクタ: 別リポの Refs owner/repo#N' "$(pre a $CREATE "$(pr_in $'Refs other/repo#12\nArch-Review: approved -- #12 の GO')")" allow
row 'コネクタ: Arch-Review の理由が空' "$(pre a $CREATE "$(pr_in $'Closes #5\nArch-Review: not-needed — ')")" deny
row 'コネクタ: 印が HTML コメント（テンプレの説明）の中だけ' "$(pre a $CREATE "$(pr_in $'<!-- Closes #5\nArch-Review: not-needed — x -->')")" deny
row 'コネクタ: 本文なし' "$(pre a $CREATE '{"owner":"O","repo":"R","title":"t","head":"f","base":"main"}')" deny
row 'gh: --body に印が両方ある' "$(pre a Bash "$(bash_in "gh pr create -R O/R --title t --body '$OK_BODY'")")" allow
row 'gh: --body に印が無い' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -b 'x'")")" deny
printf '%s\n' "$OK_BODY" > body-ok.md; printf 'x\n' > body-ng.md
row 'gh: --body-file に印がある' "$(pre a Bash "$(bash_in 'gh pr create -R O/R -t t --body-file body-ok.md')")" allow
row 'gh: --body-file に印が無い' "$(pre a Bash "$(bash_in 'cd . && gh pr create -R O/R -t t -F body-ng.md')")" deny
row 'gh: --body に $(cat <<EOF …) で印がある' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t --body \"\$(cat <<'EOF'
$OK_BODY
EOF
)\"")")" allow
row 'gh: -F - <<EOF のヒアドキュメントに印がある' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -F - <<'EOF'
$OK_BODY
EOF")")" allow
row "gh: ヒアドキュメントに ' と # があっても読める" "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -F - <<'EOF'
## Summary
don't panic
$OK_BODY
EOF")")" allow
row 'gh: -F - <<EOF のヒアドキュメントに印が無い' "$(pre a Bash "$(bash_in "gh pr create -R O/R -t t -F - <<'EOF'
x
EOF")")" deny
row 'gh: --body "$BODY"（変数で中身が分からない）' "$(pre a Bash "$(bash_in 'gh pr create -R O/R -t t --body "$BODY"')")" deny
row 'gh: --fill（本文を確かめられない）' "$(pre a Bash "$(bash_in 'gh pr create --fill')")" deny
row 'gh 以外のコマンド（echo の中の gh pr create）' "$(pre a Bash "$(bash_in "echo 'gh pr create --fill'")")" allow
row 'gh pr view は対象外' "$(pre a Bash "$(bash_in 'gh pr view 3 -R O/R')")" allow

echo
echo '=== B: 待ち忘れ（Stop） ==='
row 'PR を作っていないセッション' "$(stop b0)" allow
row 'コネクタで PR を作ると次の段を伝える' "$(post b1 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 7)")" inject
row 'PR を作って待たずに終える（1 回目）' "$(stop b1)" block
row '同じ PR で 2 回目は止めない' "$(stop b1)" allow
post b2 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 8)" >/dev/null
post b2 mcp__claude-code-remote__subscribe_pr_activity '{"repo":"O/R","pr_number":8}' '"ok"' >/dev/null
row 'PR イベントを購読してから終える' "$(stop b2)" allow
post b3 Bash "$(bash_in "gh pr create -R O/R -t t -b '$OK_BODY'")" "$(bash_out 'https://github.com/O/R/pull/9')" >/dev/null
post b3 Monitor '{"command":"gh pr checks 9 --watch"}' '"started"' >/dev/null
row 'gh で PR を作り Monitor を立ててから終える' "$(stop b3)" allow
post b4 Bash "$(bash_in "gh pr create -R O/R -t t -b '$OK_BODY'")" "$(bash_out 'https://github.com/O/R/pull/10')" >/dev/null
row 'gh で PR を作って待たずに終える' "$(stop b4)" block
post b5 $CREATE "$(pr_in "$OK_BODY")" "$(pr_out 11)" >/dev/null
row 'stop_hook_active のときは止めない' "$(stop b5 true)" allow
post b6 Bash "$(bash_in "gh pr create -R O/R -t t -b '$OK_BODY'")" '{"stdout":"","stderr":"GraphQL: was submitted too quickly"}' >/dev/null
row 'gh pr create が失敗したら記録しない' "$(stop b6)" allow

echo
echo '=== C: `## 結果` 無しのマージ（PreToolUse） ==='
mk() { post "$1" $CREATE "$(pr_in "$2" "${4:-feat}")" "$(pr_out "$3")" >/dev/null; }
mi() { printf '{"owner":"%s","repo":"R","pullNumber":%s}' "${2:-O}" "$1"; }
mk c1 "$OK_BODY" 20
row 'Closes 先に `## 結果` の記録が無い（コネクタ）' "$(pre c1 $MERGE "$(mi 20)")" deny
row '同（enable_pr_auto_merge）' "$(pre c1 $AUTO "$(mi 20)")" deny
row '同（gh pr merge 番号 -R）' "$(pre c1 Bash "$(bash_in 'gh pr merge 20 -R O/R --squash')")" deny
row '同（gh pr merge URL）' "$(pre c1 Bash "$(bash_in 'gh pr merge https://github.com/O/R/pull/20')")" deny
post c1 mcp__github__issue_write '{"method":"update","owner":"o","repo":"r","issue_number":5,"body":"本文\n\n## 結果\n- 済み"}' '"ok"' >/dev/null
row 'issue_write で `## 結果` を書いた後（owner の大小は無視）' "$(pre c1 $MERGE "$(mi 20 o)")" allow
mk c2 "$OK_BODY" 21
post c2 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":5,"body":"結果はまだ"}' '"ok"' >/dev/null
row '`## 結果` の無い body で update しても通さない' "$(pre c2 $MERGE "$(mi 21)")" deny
post c2 mcp__github__issue_read '{"method":"get","owner":"O","repo":"R","issue_number":5}' "$(printf '[{"type":"text","text":%s}]' "$(j '{"body":"x\n\n## 結果\nok"}')")" >/dev/null
row 'issue_read で `## 結果` を読んで確かめた後' "$(pre c2 $MERGE "$(mi 21)")" allow
mk c3 "$OK_BODY" 22
row 'issue_read の body に `## 結果` が無ければ通さない' "$(post c3 mcp__github__issue_read '{"method":"get","owner":"O","repo":"R","issue_number":5}' '{"body":"x"}' >/dev/null; pre c3 $MERGE "$(mi 22)")" deny
post c3 Bash "$(bash_in 'gh issue edit 5 -R O/R --body-file r.md')" "$(bash_out '')" >/dev/null
row 'gh issue edit の body-file が読めないと記録しない' "$(pre c3 $MERGE "$(mi 22)")" deny
printf 'x\n\n## 結果\n- 済み\n' > r.md
post c3 Bash "$(bash_in 'gh issue edit 5 -R O/R --body-file r.md')" "$(bash_out 'https://github.com/O/R/issues/5')" >/dev/null
row 'gh issue edit で `## 結果` を書いた後（gh pr merge）' "$(pre c3 Bash "$(bash_in 'gh pr merge 22 -R O/R')")" allow
mk c4 "$OK_BODY" 23
post c4 Bash "$(bash_in 'gh issue view 5 -R O/R')" "$(bash_out $'title: x\n--\nbody\n\n## 結果\nok')" >/dev/null
row 'gh issue view で確かめた後（ブランチ名で gh pr merge）' "$(pre c4 Bash "$(bash_in 'gh pr merge feat -R O/R')")" allow
mk c5 $'Refs #5\nArch-Review: not-needed — x' 24
row 'Refs だけの PR は止めない' "$(pre c5 $MERGE "$(mi 24)")" allow
row 'このセッションで作っていない PR は止めない' "$(pre c5 $MERGE "$(mi 99)")" allow
row '作っていない PR のマージ後に一言返す' "$(post c5 $MERGE "$(mi 99)" '"merged"')" inject
row '作った PR のマージ後は何も返さない' "$(post c5 $MERGE "$(mi 24)" '"merged"')" none
mk c6 $'Fixes other/x#3, closes #6\nArch-Review: approved — #6' 25
post c6 mcp__github__issue_write '{"method":"update","owner":"O","repo":"R","issue_number":6,"body":"## 結果\nok"}' '"ok"' >/dev/null
row '2 件 Closes のうち別リポの 1 件が未記入' "$(pre c6 $MERGE "$(mi 25)")" deny
post c6 mcp__github__issue_write '{"method":"update","owner":"other","repo":"x","issue_number":3,"body":"## Results\nok"}' '"ok"' >/dev/null
row '両方に書いた後' "$(pre c6 $MERGE "$(mi 25)")" allow
row 'セッションが違えば記録も別' "$(pre c1x $MERGE "$(mi 20)")" allow

echo
echo '=== D: 掃除（SessionStart） ==='
touch -d '40 days ago' "$CLAUDE_PLUGIN_DATA/dev-flow-gate/c1.json"
printf '{"hook_event_name":"SessionStart","session_id":"s"}' | python3 "$HOOK"
[ -e "$CLAUDE_PLUGIN_DATA/dev-flow-gate/c1.json" ] && r=kept || r=gone
row '30 日より古い状態ファイルを消す' "$r" gone
[ -e "$CLAUDE_PLUGIN_DATA/dev-flow-gate/c2.json" ] && r=kept || r=gone
row '新しい状態ファイルは残す' "$r" kept

echo
echo '=== E: 壊れた入力で落ちない ==='
out=$(printf 'not json' | python3 "$HOOK"; echo "rc=$?")
row '壊れた JSON' "$( [ "$out" = 'rc=0' ] && echo quiet || echo noisy)" quiet

rm -rf "$T"
