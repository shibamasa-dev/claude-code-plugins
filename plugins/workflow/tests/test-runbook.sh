#!/bin/bash
# runbook.py（computer use / browser use の手順記録）の受け入れ基準を実測する。2026-09-26。
# 本物の ~/.claude/runbooks を汚さないよう RUNBOOK_ROOT を $TMPDIR 配下に向ける（状態も <root>/_state に入る）。
# tool_input の形は実 transcript（~/.claude/projects/**/*.jsonl）から取った実物に合わせてある。
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/runbook.py"
export RUNBOOK_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/runbook-test.XXXX")
TODAY=$(date +%F)
row() { printf '  %-58s -> %-6s (%s 期待)\n' "$1" "$2" "$3"; }
yn() { [ "$1" = "$2" ] && echo ok || echo ng; }
# ev <session> <tool_name> <tool_input JSON>  → PostToolUse の stdin
ev() { python3 - "$@" <<'PY'
import json, sys
print(json.dumps({"session_id": sys.argv[1], "hook_event_name": "PostToolUse", "tool_name": sys.argv[2],
                  "tool_input": json.loads(sys.argv[3]), "tool_response": {}}, ensure_ascii=False))
PY
}
post() { ev "$@" | python3 "$H" hook-post; }
stop() { printf '{"session_id":"%s","hook_event_name":"Stop","stop_hook_active":false}' "$1" \
         | python3 "$H" hook-stop | grep -q '"decision": "block"' && echo block || echo pass; }
lines() { [ -f "$1" ] && wc -l < "$1" | tr -d ' ' || echo 0; }
word() { case "$1" in 0) echo zero;; 1) echo one;; 2) echo two;; 3) echo three;; *) echo many;; esac; }
leak() { word "$(grep -rlF -- "$1" "$RUNBOOK_ROOT" 2>/dev/null | wc -l | tr -d ' ')"; }
fm() { python3 - "$1" "$2" <<'PY'
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
d = dict(l.split(":", 1) for l in m.group(1).splitlines())
print(d[sys.argv[2]].strip().strip('"'))
PY
}
plus() { python3 -c "import datetime,sys; print((datetime.date.fromisoformat(sys.argv[1])+datetime.timedelta(days=int(sys.argv[2]))).isoformat())" "$1" "$2"; }

S1=a1b2c3d4-0000-4000-8000-000000000001
IB1=$RUNBOOK_ROOT/_inbox/$S1.jsonl
PW='Tr0ub4dor&3-山田太郎'
ACCT='0012345678みずほ'
BATCHPW='zQ9#取引パスワード'
CUPW='cu-秘密-Passw0rd'
JSVAL='PIN8642zz'

echo '=== 基準1: 入力値は 1 文字も残らない ==='
post $S1 mcp__claude-in-chrome__computer '{"action":"left_click","tabId":1935635015,"coordinate":[742,477]}'
n0=$(lines "$IB1")
post $S1 mcp__claude-in-chrome__computer "{\"action\":\"type\",\"tabId\":1935635015,\"text\":\"$PW\"}"
row 'type で inbox が 1 行増える' "$(word $(( $(lines "$IB1") - n0 )))" one
row 'type の text がどこにも無い' "$(leak "$PW")" zero
post $S1 mcp__claude-in-chrome__form_input "{\"tabId\":1935635056,\"ref\":\"ref_20\",\"value\":\"$ACCT\"}"
row 'form_input の value がどこにも無い' "$(leak "$ACCT")" zero
n0=$(lines "$IB1")
post $S1 mcp__claude-in-chrome__browser_batch "{\"actions\":[{\"name\":\"computer\",\"input\":{\"action\":\"left_click\",\"tabId\":1,\"ref\":\"ref_9\"}},{\"name\":\"computer\",\"input\":{\"action\":\"type\",\"tabId\":1,\"text\":\"$BATCHPW\"}}]}"
row 'browser_batch は 1 アクション 1 行に展開（2 行増える）' "$(word $(( $(lines "$IB1") - n0 )))" two
row 'browser_batch 内の type の text がどこにも無い' "$(leak "$BATCHPW")" zero
post $S1 mcp__computer-use__computer_batch "{\"actions\":[{\"action\":\"left_click\",\"coordinate\":[342,14]},{\"action\":\"type\",\"text\":\"$CUPW\"},{\"action\":\"screenshot\",\"scale\":0.5}]}"
row 'computer_batch（computer use）の type もどこにも無い' "$(leak "$CUPW")" zero
post $S1 mcp__claude-in-chrome__javascript_tool "{\"action\":\"javascript_exec\",\"tabId\":1935634610,\"text\":\"document.querySelector('#pin').value='$JSVAL'\"}"
row 'javascript_tool のコードがどこにも無い' "$(leak "$JSVAL")" zero
got=$(python3 - "$IB1" "$PW" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
t = [r for r in rows if r.get("action") == "type"][0]
print("ok" if t["masked"] == {"text": len(sys.argv[2])} and t["kind"] == "op" else "ng")
PY
)
row '伏せた値は文字数だけ残り、type は操作に分類される' "$got" ok
got=$(python3 - "$IB1" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
s = [r for r in rows if r.get("action") == "screenshot"]
print("ok" if s and s[0]["kind"] == "read" and s[0]["shot"] is True else "ng")
PY
)
row 'screenshot は読み取り・shot=true' "$got" ok
n0=$(lines "$IB1")
post $S1 mcp__playwright__browser_click '{"element":"ログイン","ref":"e12"}'
row 'Playwright は記録しない' "$(word $(( $(lines "$IB1") - n0 )))" zero

echo '=== 基準2: URL のクエリ・フラグメントを落とす ==='
post $S1 mcp__claude-in-chrome__navigate '{"tabId":1935635015,"url":"https://www.marutsu.co.jp/GoodsListNavi.jsp?q=CH32V003#top"}'
post $S1 mcp__Claude_Browser__navigate '{"url":"https://user:hunter2pw@example.com/login?next=/billing"}'
got=$(tail -2 "$IB1" | python3 -c 'import json,sys; print(" ".join(json.loads(l)["url"] for l in sys.stdin))')
row 'クエリとフラグメントが消える' "$(yn "${got%% *}" https://www.marutsu.co.jp/GoodsListNavi.jsp)" ok
row 'userinfo とクエリが消える' "$(yn "${got##* }" https://example.com/login)" ok
row 'クエリ値（CH32V003）がどこにも無い' "$(leak CH32V003)" zero
row 'URL 内のパスワードがどこにも無い' "$(leak hunter2pw)" zero

echo '=== 基準3: Stop ==='
S2=a1b2c3d4-0000-4000-8000-000000000002
post $S2 mcp__claude-in-chrome__navigate '{"tabId":1,"url":"https://example.com/"}'
post $S2 mcp__claude-in-chrome__computer '{"action":"left_click","tabId":1,"coordinate":[10,20]}'
for i in 1 2 3 4 5; do post $S2 mcp__claude-in-chrome__computer '{"action":"screenshot","tabId":1}'; done
r=""; for i in 1 2 3 4; do r="$r$(stop $S2)"; done
row '操作 2 件（読み取りは何件でも）なら Stop 4 回とも止めない' "$( [ "$r" = passpasspasspass ] && echo pass || echo block)" pass
post $S2 mcp__claude-in-chrome__computer '{"action":"key","tabId":1,"text":"Return"}'
row '操作 3 件: 1 回目の Stop は止めない' "$(stop $S2)" pass
row '操作 3 件: 2 回目の Stop は止めない' "$(stop $S2)" pass
OUT=$(printf '{"session_id":"%s","hook_event_name":"Stop"}' $S2 | python3 "$H" hook-stop)
row '操作 3 件: 3 回目（K 回目）の Stop で block' "$(echo "$OUT" | grep -q '"decision": "block"' && echo block || echo pass)" block
got=$(echo "$OUT" | python3 -c 'import json,sys; r=json.load(sys.stdin)["reason"]; import re; print(len(re.findall(r"\brunbook (new|use|dismiss) .*--session '"$S2"'", r)))')
row 'block 文面に --session 実ID 入りの new/use/dismiss が 3 つ' "$(word "$got")" three
row 'stop_hook_active 中は止めない' "$(printf '{"session_id":"%s","stop_hook_active":true}' $S2 | python3 "$H" hook-stop | grep -q block && echo block || echo pass)" pass
python3 "$H" dismiss --session $S2 --why "テスト: 検証だけで手順ではない" >/dev/null
r=""; for i in 1 2 3 4; do r="$r$(stop $S2)"; done
row 'dismiss の後は Stop 4 回とも止めない' "$( [ "$r" = passpasspasspass ] && echo pass || echo block)" pass
row 'dismiss で inbox が消える' "$( [ -e "$RUNBOOK_ROOT/_inbox/$S2.jsonl" ] && echo ng || echo ok)" ok
row 'dismiss の理由が状態に残る' "$(grep -q '検証だけで手順ではない' "$RUNBOOK_ROOT/_state/$S2.json" && echo ok || echo ng)" ok
row 'ブラウザを触っていないセッションは状態ファイルを作らない' "$(stop a1b2c3d4-0000-4000-8000-00000000ffff >/dev/null; [ -e "$RUNBOOK_ROOT/_state/a1b2c3d4-0000-4000-8000-00000000ffff.json" ] && echo ng || echo ok)" ok

echo '=== 基準4: new ==='
n_inbox=$(lines "$IB1")
OUT=$(python3 "$H" new --session $S1 --slug 請求書ダウンロード --recurrence monthly --title "freee 請求書 PDF の取得")
D1="$RUNBOOK_ROOT/${TODAY}_請求書ダウンロード"
row 'フォルダができる（表示されるパスと一致）' "$( [ -d "$D1" ] && [ "$(echo "$OUT" | head -1)" = "$D1" ] && echo ok || echo ng)" ok
row 'steps.jsonl に inbox の全行が移る' "$(yn "$(lines "$D1/steps.jsonl")" "$n_inbox")" ok
row 'inbox から消える' "$( [ -e "$IB1" ] && echo ng || echo ok)" ok
got=$(python3 - "$D1/runbook.md" <<'PY'
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
keys = [l.split(":", 1)[0] for l in m.group(1).splitlines()]
want = ["title", "created", "last_used", "uses", "recurrence", "keep_until", "status", "sessions", "gif"]
print("ok" if keys == want else "ng:" + ",".join(keys))
PY
)
row 'frontmatter の 9 キーが仕様どおりの並び' "$got" ok
got=$(grep '^## ' "$D1/runbook.md" | sed -e 's/^## //' -e 's/（.*//' | tr '\n' '|')
row '本文の 7 見出しが SKILL.md と同じ並び' "$(yn "$got" '目的|前提・入力値|手順|分岐・つまずき|止める地点|検証|録画|')" ok
row 'monthly の keep_until = created+45' "$(yn "$(fm "$D1/runbook.md" keep_until)" "$(plus "$TODAY" 45)")" ok
row 'status=draft・uses=1・sessions に実ID' "$( [ "$(fm "$D1/runbook.md" status)" = draft ] && [ "$(fm "$D1/runbook.md" uses)" = 1 ] && [ "$(fm "$D1/runbook.md" sessions)" = "[$S1]" ] && echo ok || echo ng)" ok
row '同じフォルダ名の new は拒否' "$(python3 "$H" new --session $S1 --slug 請求書ダウンロード --recurrence monthly >/dev/null 2>&1 && echo ok || echo refuse)" refuse
row '不正な recurrence は拒否' "$(python3 "$H" new --session $S1 --slug x --recurrence weekly >/dev/null 2>&1 && echo ok || echo refuse)" refuse

echo '=== new --gif ==='
S5=a1b2c3d4-0000-4000-8000-000000000005
GIF=$(mktemp "${TMPDIR:-/tmp}/runbook-rec.XXXX").gif; : > "$GIF"
python3 "$H" new --session $S5 --slug gif-ok --recurrence once --gif "$GIF" >/dev/null
row 'GIF がフォルダへ移り、frontmatter が新しいパスを指す' "$( [ -f "$RUNBOOK_ROOT/${TODAY}_gif-ok/$(basename "$GIF")" ] && [ ! -e "$GIF" ] && [ "$(fm "$RUNBOOK_ROOT/${TODAY}_gif-ok/runbook.md" gif)" = "$RUNBOOK_ROOT/${TODAY}_gif-ok/$(basename "$GIF")" ] && echo ok || echo ng)" ok
# TMPDIR は macOS だと末尾に / が付く。runbook.py は Path で正規化して記録するので、期待値も // を作らない
T="${TMPDIR:-/tmp}"; MISSING="${T%/}/無い録画.gif"
python3 "$H" new --session $S5 --slug gif-missing --recurrence once --gif "$MISSING" >/dev/null 2>&1; rc=$?
row '移せない GIF は元のパスを記録して正常終了' "$( [ $rc = 0 ] && [ "$(fm "$RUNBOOK_ROOT/${TODAY}_gif-missing/runbook.md" gif)" = "$MISSING" ] && echo ok || echo ng)" ok
FAKE=$(mktemp -d "${TMPDIR:-/tmp}/runbook-fakebin.XXXX"); printf '#!/bin/bash\nexec sleep 30\n' > "$FAKE/mv"; chmod +x "$FAKE/mv"
t0=$(date +%s)
PATH="$FAKE:$PATH" python3 "$H" new --session $S5 --slug gif-hang --recurrence once --gif ~/Downloads/rec.gif >/dev/null 2>&1; rc=$?
dt=$(( $(date +%s) - t0 ))
row 'mv がハングしても 10 秒で打ち切り、元のパスを記録して正常終了' "$( [ $rc = 0 ] && [ $dt -lt 15 ] && [ "$(fm "$RUNBOOK_ROOT/${TODAY}_gif-hang/runbook.md" gif)" = "$HOME/Downloads/rec.gif" ] && echo ok || echo ng)" ok

echo '=== 基準5: use ==='
# 1 回目を 2026-08-01 に作った体にする（keep_until の延長が見えるように）
python3 - "$D1/runbook.md" <<'PY'
import re, sys
p = sys.argv[1]; t = open(p, encoding="utf-8").read()
for k, v in (("created", "2026-08-01"), ("last_used", "2026-08-01"), ("keep_until", "2026-09-15")):
    t = re.sub(rf"^{k}: .*$", f"{k}: {v}", t, count=1, flags=re.M)
open(p, "w", encoding="utf-8").write(t)
PY
S3=a1b2c3d4-0000-4000-8000-000000000003
post $S3 mcp__claude-in-chrome__navigate '{"tabId":2,"url":"https://secure.freee.co.jp/"}'
post $S3 mcp__claude-in-chrome__computer '{"action":"left_click","tabId":2,"coordinate":[100,200]}'
OUT=$(python3 "$H" use "$(basename "$D1")" --session $S3)
row 'uses が 2 になる' "$(yn "$(fm "$D1/runbook.md" uses)" 2)" ok
row 'monthly の keep_until が last_used(今日)+45 に延びる' "$(yn "$(fm "$D1/runbook.md" keep_until)" "$(plus "$TODAY" 45)")" ok
row 'last_used が今日になる' "$(yn "$(fm "$D1/runbook.md" last_used)" "$TODAY")" ok
row 'スキル化提案の文言が出る' "$(echo "$OUT" | grep -q '2回目の実行。スキル化を提案する（skill-creator に runbook.md を渡す）' && echo ok || echo ng)" ok
row "今回のログが steps-${TODAY}.jsonl に積まれる" "$(yn "$(lines "$D1/steps-$TODAY.jsonl")" 2)" ok
row 'sessions に 2 セッションとも載る' "$(yn "$(fm "$D1/runbook.md" sessions)" "[$S1, $S3]")" ok
row '本文（見出し）は壊れない' "$(yn "$(grep -c '^## ' "$D1/runbook.md")" 7)" ok
# yearly は last_used+400、once は created+60 のまま
DY="$RUNBOOK_ROOT/${TODAY}_gif-ok"
sed -i '' 's/^recurrence: once$/recurrence: yearly/' "$DY/runbook.md"
python3 "$H" use "$DY" --session $S3 >/dev/null
row 'yearly の keep_until は last_used+400' "$(yn "$(fm "$DY/runbook.md" keep_until)" "$(plus "$TODAY" 400)")" ok
row 'root の外のフォルダは use できない' "$(python3 "$H" use "$TMPDIR" --session $S3 >/dev/null 2>&1 && echo ok || echo refuse)" refuse

echo '=== 基準6: sweep ==='
mk() { mkdir -p "$RUNBOOK_ROOT/$1"; printf -- '---\ntitle: "%s"\ncreated: 2026-06-01\nlast_used: 2026-06-01\nuses: 1\nrecurrence: once\nkeep_until: %s\nstatus: %s\nsessions: [x]\ngif: null\n---\n\n# t\n' "$1" "$2" "$3" > "$RUNBOOK_ROOT/$1/runbook.md"; }
mk 2026-06-01_expired-draft 2026-07-31 draft
mk 2026-06-02_expired-promoted 2026-07-31 promoted
mk 2026-06-03_fresh-draft 2099-01-01 draft
mkdir -p "$RUNBOOK_ROOT/2026-06-04_broken"; echo '# frontmatter なし' > "$RUNBOOK_ROOT/2026-06-04_broken/runbook.md"
echo 'メモ' > "$RUNBOOK_ROOT/notes.txt"
: > "$RUNBOOK_ROOT/_inbox/old-session.jsonl"; touch -t "$(date -v-20d +%Y%m%d%H%M)" "$RUNBOOK_ROOT/_inbox/old-session.jsonl"
: > "$RUNBOOK_ROOT/_inbox/recent-session.jsonl"
exists() { [ -e "$RUNBOOK_ROOT/$1" ] && echo kept || echo gone; }
OUT=$(python3 "$H" sweep)
row 'dry-run は期限切れ draft を一覧に出す' "$(echo "$OUT" | grep -q 'expired-draft' && echo ok || echo ng)" ok
row 'dry-run では何も消えない（期限切れ draft）' "$(exists 2026-06-01_expired-draft)" kept
row 'dry-run では何も消えない（古い inbox）' "$(exists _inbox/old-session.jsonl)" kept
python3 "$H" sweep --apply >/dev/null
row 'apply: draft かつ期限切れは消える' "$(exists 2026-06-01_expired-draft)" gone
row 'apply: promoted は期限切れでも残る' "$(exists 2026-06-02_expired-promoted)" kept
row 'apply: 期限前の draft は残る' "$(exists 2026-06-03_fresh-draft)" kept
row 'apply: frontmatter が読めないものは残す' "$(exists 2026-06-04_broken)" kept
row 'apply: root 直下の runbook 以外のファイルは残る' "$(exists notes.txt)" kept
row 'apply: 14 日超の inbox は消える' "$(exists _inbox/old-session.jsonl)" gone
row 'apply: 新しい inbox は残る' "$(exists _inbox/recent-session.jsonl)" kept
row 'apply: 使用中の runbook は残る' "$(exists "${TODAY}_請求書ダウンロード")" kept

echo '=== 基準7: promote ==='
SK=$(mktemp -d "${TMPDIR:-/tmp}/runbook-skill.XXXX")
row 'SKILL.md の無いスキルを渡すとエラー' "$(python3 "$H" promote "$(basename "$D1")" --skill "$SK" >/dev/null 2>&1 && echo ok || echo refuse)" refuse
row 'エラーのとき runbook は消えない' "$(exists "${TODAY}_請求書ダウンロード")" kept
echo '# skill' > "$SK/SKILL.md"
row 'root の外のフォルダは promote できない' "$(python3 "$H" promote "$SK" --skill "$SK" >/dev/null 2>&1 && echo ok || echo refuse)" refuse
row 'SKILL.md があれば promote できる' "$(python3 "$H" promote "$(basename "$D1")" --skill "$SK" >/dev/null 2>&1 && echo ok || echo refuse)" ok
row 'promote で runbook フォルダが消える' "$(exists "${TODAY}_請求書ダウンロード")" gone
row 'スキル側は残る' "$( [ -f "$SK/SKILL.md" ] && echo kept || echo gone)" kept

echo '=== 基準8: SessionStart の sweep は 1 日 1 回 ==='
date -v-1d +%F > "$RUNBOOK_ROOT/.last_sweep"
mk 2026-06-05_expired-a 2026-07-31 draft
OUT=$(echo '{"session_id":"s","hook_event_name":"SessionStart","source":"startup"}' | python3 "$H" hook-session-start)
row '昨日が最後なら今日の 1 回目で sweep する' "$(exists 2026-06-05_expired-a)" gone
row '消したときだけ 1 行出す' "$(echo "$OUT" | grep -q '^runbooks: 期限切れ 1件を削除（2026-06-05_expired-a）' && [ "$(echo "$OUT" | wc -l | tr -d ' ')" = 1 ] && echo ok || echo ng)" ok
mk 2026-06-06_expired-b 2026-07-31 draft
OUT=$(echo '{"session_id":"s","hook_event_name":"SessionStart","source":"startup"}' | python3 "$H" hook-session-start)
row '同じ日の 2 回目は sweep しない' "$(exists 2026-06-06_expired-b)" kept
row '同じ日の 2 回目は何も出さない' "$( [ -z "$OUT" ] && echo ok || echo ng)" ok

echo '=== 基準9: 壊れた入力でも exit 0 ==='
chk() { local out err rc; out=$(printf '%s' "$2" | python3 "$H" "$1" 2>"$RUNBOOK_ROOT/.err"); rc=$?
        [ $rc = 0 ] && [ ! -s "$RUNBOOK_ROOT/.err" ] && [ -z "$out" ] && echo ok || echo ng; }
for h in hook-post hook-stop hook-session-start; do
  row "$h: 壊れた JSON" "$(chk $h '{"session_id": "x", broken')" ok
  row "$h: 空の stdin" "$(chk $h '')" ok
done
row 'hook-post: 未知の tool_name' "$(chk hook-post '{"session_id":"a1b2c3d4-0000-4000-8000-000000000009","tool_name":"Bash","tool_input":{"command":"ls"}}')" ok
row 'hook-post: 未知の tool_name では inbox を作らない' "$(exists _inbox/a1b2c3d4-0000-4000-8000-000000000009.jsonl)" gone
row 'hook-post: tool_input が文字列' "$(chk hook-post '{"session_id":"a1b2c3d4-0000-4000-8000-000000000009","tool_name":"mcp__claude-in-chrome__computer","tool_input":"x"}')" ok
row 'hook-post: actions が壊れた batch' "$(chk hook-post '{"session_id":"a1b2c3d4-0000-4000-8000-000000000009","tool_name":"mcp__computer-use__computer_batch","tool_input":{"actions":[1,"x",null,{"name":3,"input":"y"}]}}')" ok
row 'hook-post: session_id が無い・パス区切りを含む' "$(chk hook-post '{"session_id":"../../etc","tool_name":"mcp__claude-in-chrome__computer","tool_input":{}}')" ok
row 'hook-stop: session_id が無い' "$(chk hook-stop '{"hook_event_name":"Stop"}')" ok

rm -rf "$RUNBOOK_ROOT" "$SK" "$FAKE"
