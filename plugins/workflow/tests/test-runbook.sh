#!/bin/bash
# Live check of the acceptance criteria of runbook.py (recording computer use / browser use procedures). 2026-09-26.
# RUNBOOK_ROOT points under $TMPDIR so the real ~/.claude/runbooks stays clean (state also goes to <root>/_state).
# The tool_input shapes match real ones taken from actual transcripts (~/.claude/projects/**/*.jsonl).
# The secret values and the task slug below deliberately use Japanese (multibyte) text, as real user input does.
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/runbook.py"
export RUNBOOK_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/runbook-test.XXXX")
TODAY=$(date +%F)
row() { printf '  %-58s -> %-6s (expect %s)\n' "$1" "$2" "$3"; }
yn() { [ "$1" = "$2" ] && echo ok || echo ng; }
# ev <session> <tool_name> <tool_input JSON>  -> stdin for PostToolUse
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

echo '=== criterion 1: not a single character of input values is kept ==='
post $S1 mcp__claude-in-chrome__computer '{"action":"left_click","tabId":1935635015,"coordinate":[742,477]}'
n0=$(lines "$IB1")
post $S1 mcp__claude-in-chrome__computer "{\"action\":\"type\",\"tabId\":1935635015,\"text\":\"$PW\"}"
row 'type adds one line to the inbox' "$(word $(( $(lines "$IB1") - n0 )))" one
row 'the type text is nowhere' "$(leak "$PW")" zero
post $S1 mcp__claude-in-chrome__form_input "{\"tabId\":1935635056,\"ref\":\"ref_20\",\"value\":\"$ACCT\"}"
row 'the form_input value is nowhere' "$(leak "$ACCT")" zero
n0=$(lines "$IB1")
post $S1 mcp__claude-in-chrome__browser_batch "{\"actions\":[{\"name\":\"computer\",\"input\":{\"action\":\"left_click\",\"tabId\":1,\"ref\":\"ref_9\"}},{\"name\":\"computer\",\"input\":{\"action\":\"type\",\"tabId\":1,\"text\":\"$BATCHPW\"}}]}"
row 'browser_batch expands to one line per action (+2 lines)' "$(word $(( $(lines "$IB1") - n0 )))" two
row 'the type text inside browser_batch is nowhere' "$(leak "$BATCHPW")" zero
post $S1 mcp__computer-use__computer_batch "{\"actions\":[{\"action\":\"left_click\",\"coordinate\":[342,14]},{\"action\":\"type\",\"text\":\"$CUPW\"},{\"action\":\"screenshot\",\"scale\":0.5}]}"
row 'the type in computer_batch (computer use) is nowhere either' "$(leak "$CUPW")" zero
post $S1 mcp__claude-in-chrome__javascript_tool "{\"action\":\"javascript_exec\",\"tabId\":1935634610,\"text\":\"document.querySelector('#pin').value='$JSVAL'\"}"
row 'the javascript_tool code is nowhere' "$(leak "$JSVAL")" zero
got=$(python3 - "$IB1" "$PW" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
t = [r for r in rows if r.get("action") == "type"][0]
print("ok" if t["masked"] == {"text": len(sys.argv[2])} and t["kind"] == "op" else "ng")
PY
)
row 'masked values keep only their length; type is an operation' "$got" ok
got=$(python3 - "$IB1" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
s = [r for r in rows if r.get("action") == "screenshot"]
print("ok" if s and s[0]["kind"] == "read" and s[0]["shot"] is True else "ng")
PY
)
row 'screenshot is a read with shot=true' "$got" ok
n0=$(lines "$IB1")
post $S1 mcp__playwright__browser_click '{"element":"Log in","ref":"e12"}'
row 'Playwright is not recorded' "$(word $(( $(lines "$IB1") - n0 )))" zero

echo '=== criterion 2: drop the URL query and fragment ==='
post $S1 mcp__claude-in-chrome__navigate '{"tabId":1935635015,"url":"https://www.marutsu.co.jp/GoodsListNavi.jsp?q=CH32V003#top"}'
post $S1 mcp__Claude_Browser__navigate '{"url":"https://user:hunter2pw@example.com/login?next=/billing"}'
got=$(tail -2 "$IB1" | python3 -c 'import json,sys; print(" ".join(json.loads(l)["url"] for l in sys.stdin))')
row 'query and fragment are dropped' "$(yn "${got%% *}" https://www.marutsu.co.jp/GoodsListNavi.jsp)" ok
row 'userinfo and query are dropped' "$(yn "${got##* }" https://example.com/login)" ok
row 'the query value (CH32V003) is nowhere' "$(leak CH32V003)" zero
row 'the password in the URL is nowhere' "$(leak hunter2pw)" zero

echo '=== criterion 3: Stop ==='
S2=a1b2c3d4-0000-4000-8000-000000000002
post $S2 mcp__claude-in-chrome__navigate '{"tabId":1,"url":"https://example.com/"}'
post $S2 mcp__claude-in-chrome__computer '{"action":"left_click","tabId":1,"coordinate":[10,20]}'
for i in 1 2 3 4 5; do post $S2 mcp__claude-in-chrome__computer '{"action":"screenshot","tabId":1}'; done
r=""; for i in 1 2 3 4; do r="$r$(stop $S2)"; done
row '2 operations (any number of reads): none of 4 Stops block' "$( [ "$r" = passpasspasspass ] && echo pass || echo block)" pass
post $S2 mcp__claude-in-chrome__computer '{"action":"key","tabId":1,"text":"Return"}'
row '3 operations: 1st Stop does not block' "$(stop $S2)" pass
row '3 operations: 2nd Stop does not block' "$(stop $S2)" pass
OUT=$(printf '{"session_id":"%s","hook_event_name":"Stop"}' $S2 | python3 "$H" hook-stop)
row '3 operations: 3rd (K-th) Stop blocks' "$(echo "$OUT" | grep -q '"decision": "block"' && echo block || echo pass)" block
got=$(echo "$OUT" | python3 -c 'import json,sys,re; r=json.load(sys.stdin)["reason"]; print(len(re.findall(re.escape("python3 \"" + sys.argv[1] + "\" ") + r"(new|use|dismiss) .*--session '"$S2"'", r)))' "$H")
row 'block message has new/use/dismiss with the hook path and the real --session id' "$(word "$got")" three
row 'no block while stop_hook_active' "$(printf '{"session_id":"%s","stop_hook_active":true}' $S2 | python3 "$H" hook-stop | grep -q block && echo block || echo pass)" pass
python3 "$H" dismiss --session $S2 --why "test: just a check, not a procedure" >/dev/null
r=""; for i in 1 2 3 4; do r="$r$(stop $S2)"; done
row 'after dismiss, none of 4 Stops block' "$( [ "$r" = passpasspasspass ] && echo pass || echo block)" pass
row 'dismiss removes the inbox' "$( [ -e "$RUNBOOK_ROOT/_inbox/$S2.jsonl" ] && echo ng || echo ok)" ok
row 'the dismiss reason stays in the state' "$(grep -q 'just a check, not a procedure' "$RUNBOOK_ROOT/_state/$S2.json" && echo ok || echo ng)" ok
row 'no state file for a session that never touched a browser' "$(stop a1b2c3d4-0000-4000-8000-00000000ffff >/dev/null; [ -e "$RUNBOOK_ROOT/_state/a1b2c3d4-0000-4000-8000-00000000ffff.json" ] && echo ng || echo ok)" ok

echo '=== criterion 4: new ==='
n_inbox=$(lines "$IB1")
OUT=$(python3 "$H" new --session $S1 --slug 請求書ダウンロード --recurrence monthly --title "Download the freee invoice PDF")
D1="$RUNBOOK_ROOT/${TODAY}_請求書ダウンロード"
row 'folder is created (matches the printed path)' "$( [ -d "$D1" ] && [ "$(echo "$OUT" | head -1)" = "$D1" ] && echo ok || echo ng)" ok
row 'all inbox lines move to steps.jsonl' "$(yn "$(lines "$D1/steps.jsonl")" "$n_inbox")" ok
row 'removed from the inbox' "$( [ -e "$IB1" ] && echo ng || echo ok)" ok
got=$(python3 - "$D1/runbook.md" <<'PY'
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
keys = [l.split(":", 1)[0] for l in m.group(1).splitlines()]
want = ["title", "created", "last_used", "uses", "recurrence", "keep_until", "status", "sessions", "gif"]
print("ok" if keys == want else "ng:" + ",".join(keys))
PY
)
row 'the 9 frontmatter keys are in the specified order' "$got" ok
got=$(grep '^## ' "$D1/runbook.md" | sed -e 's/^## //' -e 's/ (.*//' | tr '\n' '|')
row 'the 7 body headings are in the specified order' "$(yn "$got" 'Goal|Prerequisites and inputs|Steps|Branches and pitfalls|Stop points|Verification|Recording|')" ok
row 'monthly keep_until = created+45' "$(yn "$(fm "$D1/runbook.md" keep_until)" "$(plus "$TODAY" 45)")" ok
row 'status=draft, uses=1, real id in sessions' "$( [ "$(fm "$D1/runbook.md" status)" = draft ] && [ "$(fm "$D1/runbook.md" uses)" = 1 ] && [ "$(fm "$D1/runbook.md" sessions)" = "[$S1]" ] && echo ok || echo ng)" ok
row 'new with an existing folder name is refused' "$(python3 "$H" new --session $S1 --slug 請求書ダウンロード --recurrence monthly >/dev/null 2>&1 && echo ok || echo refuse)" refuse
row 'an invalid recurrence is refused' "$(python3 "$H" new --session $S1 --slug x --recurrence weekly >/dev/null 2>&1 && echo ok || echo refuse)" refuse

echo '=== new --gif ==='
S5=a1b2c3d4-0000-4000-8000-000000000005
GIF=$(mktemp "${TMPDIR:-/tmp}/runbook-rec.XXXX").gif; : > "$GIF"
python3 "$H" new --session $S5 --slug gif-ok --recurrence once --gif "$GIF" >/dev/null
row 'GIF moves into the folder and the frontmatter points at it' "$( [ -f "$RUNBOOK_ROOT/${TODAY}_gif-ok/$(basename "$GIF")" ] && [ ! -e "$GIF" ] && [ "$(fm "$RUNBOOK_ROOT/${TODAY}_gif-ok/runbook.md" gif)" = "$RUNBOOK_ROOT/${TODAY}_gif-ok/$(basename "$GIF")" ] && echo ok || echo ng)" ok
# On macOS TMPDIR ends with /. runbook.py records a normalized path, so the expected value must not contain //
T="${TMPDIR:-/tmp}"; MISSING="${T%/}/missing-recording.gif"
python3 "$H" new --session $S5 --slug gif-missing --recurrence once --gif "$MISSING" >/dev/null 2>&1; rc=$?
row 'a GIF that cannot be moved: original path recorded, exit 0' "$( [ $rc = 0 ] && [ "$(fm "$RUNBOOK_ROOT/${TODAY}_gif-missing/runbook.md" gif)" = "$MISSING" ] && echo ok || echo ng)" ok
FAKE=$(mktemp -d "${TMPDIR:-/tmp}/runbook-fakebin.XXXX"); printf '#!/bin/bash\nexec sleep 30\n' > "$FAKE/mv"; chmod +x "$FAKE/mv"
t0=$(date +%s)
PATH="$FAKE:$PATH" python3 "$H" new --session $S5 --slug gif-hang --recurrence once --gif ~/Downloads/rec.gif >/dev/null 2>&1; rc=$?
dt=$(( $(date +%s) - t0 ))
row 'a hanging mv is cut off in 10s, original path recorded, exit 0' "$( [ $rc = 0 ] && [ $dt -lt 15 ] && [ "$(fm "$RUNBOOK_ROOT/${TODAY}_gif-hang/runbook.md" gif)" = "$HOME/Downloads/rec.gif" ] && echo ok || echo ng)" ok

echo '=== criterion 5: use ==='
# pretend the first run was on 2026-08-01 (so the keep_until extension is visible)
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
row 'uses becomes 2' "$(yn "$(fm "$D1/runbook.md" uses)" 2)" ok
row 'monthly keep_until extends to last_used (today)+45' "$(yn "$(fm "$D1/runbook.md" keep_until)" "$(plus "$TODAY" 45)")" ok
row 'last_used becomes today' "$(yn "$(fm "$D1/runbook.md" last_used)" "$TODAY")" ok
row 'the skill proposal message is printed' "$(echo "$OUT" | grep -q 'Run #2. Propose turning it into a skill (give runbook.md to skill-creator)' && echo ok || echo ng)" ok
row "this run's log goes to steps-${TODAY}.jsonl" "$(yn "$(lines "$D1/steps-$TODAY.jsonl")" 2)" ok
row 'both sessions are listed in sessions' "$(yn "$(fm "$D1/runbook.md" sessions)" "[$S1, $S3]")" ok
row 'the body (headings) stays intact' "$(yn "$(grep -c '^## ' "$D1/runbook.md")" 7)" ok
# yearly is last_used+400; once stays created+60
DY="$RUNBOOK_ROOT/${TODAY}_gif-ok"
sed -i '' 's/^recurrence: once$/recurrence: yearly/' "$DY/runbook.md"
python3 "$H" use "$DY" --session $S3 >/dev/null
row 'yearly keep_until is last_used+400' "$(yn "$(fm "$DY/runbook.md" keep_until)" "$(plus "$TODAY" 400)")" ok
row 'a folder outside root cannot be used' "$(python3 "$H" use "$TMPDIR" --session $S3 >/dev/null 2>&1 && echo ok || echo refuse)" refuse

echo '=== criterion 6: sweep ==='
mk() { mkdir -p "$RUNBOOK_ROOT/$1"; printf -- '---\ntitle: "%s"\ncreated: 2026-06-01\nlast_used: 2026-06-01\nuses: 1\nrecurrence: once\nkeep_until: %s\nstatus: %s\nsessions: [x]\ngif: null\n---\n\n# t\n' "$1" "$2" "$3" > "$RUNBOOK_ROOT/$1/runbook.md"; }
mk 2026-06-01_expired-draft 2026-07-31 draft
mk 2026-06-02_expired-promoted 2026-07-31 promoted
mk 2026-06-03_fresh-draft 2099-01-01 draft
mkdir -p "$RUNBOOK_ROOT/2026-06-04_broken"; echo '# no frontmatter' > "$RUNBOOK_ROOT/2026-06-04_broken/runbook.md"
echo 'notes' > "$RUNBOOK_ROOT/notes.txt"
: > "$RUNBOOK_ROOT/_inbox/old-session.jsonl"; touch -t "$(date -v-20d +%Y%m%d%H%M)" "$RUNBOOK_ROOT/_inbox/old-session.jsonl"
: > "$RUNBOOK_ROOT/_inbox/recent-session.jsonl"
exists() { [ -e "$RUNBOOK_ROOT/$1" ] && echo kept || echo gone; }
OUT=$(python3 "$H" sweep)
row 'dry-run lists the expired draft' "$(echo "$OUT" | grep -q 'expired-draft' && echo ok || echo ng)" ok
row 'dry-run deletes nothing (expired draft)' "$(exists 2026-06-01_expired-draft)" kept
row 'dry-run deletes nothing (old inbox)' "$(exists _inbox/old-session.jsonl)" kept
python3 "$H" sweep --apply >/dev/null
row 'apply: an expired draft is deleted' "$(exists 2026-06-01_expired-draft)" gone
row 'apply: promoted stays even when expired' "$(exists 2026-06-02_expired-promoted)" kept
row 'apply: a draft not yet due stays' "$(exists 2026-06-03_fresh-draft)" kept
row 'apply: unreadable frontmatter stays' "$(exists 2026-06-04_broken)" kept
row 'apply: non-runbook files directly under root stay' "$(exists notes.txt)" kept
row 'apply: inbox older than 14 days is deleted' "$(exists _inbox/old-session.jsonl)" gone
row 'apply: a recent inbox stays' "$(exists _inbox/recent-session.jsonl)" kept
row 'apply: a runbook in use stays' "$(exists "${TODAY}_請求書ダウンロード")" kept

echo '=== criterion 7: promote ==='
SK=$(mktemp -d "${TMPDIR:-/tmp}/runbook-skill.XXXX")
row 'error when the skill has no SKILL.md' "$(python3 "$H" promote "$(basename "$D1")" --skill "$SK" >/dev/null 2>&1 && echo ok || echo refuse)" refuse
row 'on error the runbook is not deleted' "$(exists "${TODAY}_請求書ダウンロード")" kept
echo '# skill' > "$SK/SKILL.md"
row 'a folder outside root cannot be promoted' "$(python3 "$H" promote "$SK" --skill "$SK" >/dev/null 2>&1 && echo ok || echo refuse)" refuse
row 'promote works when SKILL.md exists' "$(python3 "$H" promote "$(basename "$D1")" --skill "$SK" >/dev/null 2>&1 && echo ok || echo refuse)" ok
row 'promote deletes the runbook folder' "$(exists "${TODAY}_請求書ダウンロード")" gone
row 'the skill stays' "$( [ -f "$SK/SKILL.md" ] && echo kept || echo gone)" kept

echo '=== criterion 8: SessionStart sweeps once a day ==='
date -v-1d +%F > "$RUNBOOK_ROOT/.last_sweep"
mk 2026-06-05_expired-a 2026-07-31 draft
OUT=$(echo '{"session_id":"s","hook_event_name":"SessionStart","source":"startup"}' | python3 "$H" hook-session-start)
row 'last sweep yesterday: the first session today sweeps' "$(exists 2026-06-05_expired-a)" gone
row 'prints one line only when it deleted something' "$(echo "$OUT" | grep -q '^runbooks: deleted 1 expired (2026-06-05_expired-a)' && [ "$(echo "$OUT" | wc -l | tr -d ' ')" = 1 ] && echo ok || echo ng)" ok
mk 2026-06-06_expired-b 2026-07-31 draft
OUT=$(echo '{"session_id":"s","hook_event_name":"SessionStart","source":"startup"}' | python3 "$H" hook-session-start)
row 'no sweep on the 2nd session of the same day' "$(exists 2026-06-06_expired-b)" kept
row 'no output on the 2nd session of the same day' "$( [ -z "$OUT" ] && echo ok || echo ng)" ok

echo '=== criterion 9: exit 0 even on broken input ==='
chk() { local out err rc; out=$(printf '%s' "$2" | python3 "$H" "$1" 2>"$RUNBOOK_ROOT/.err"); rc=$?
        [ $rc = 0 ] && [ ! -s "$RUNBOOK_ROOT/.err" ] && [ -z "$out" ] && echo ok || echo ng; }
for h in hook-post hook-stop hook-session-start; do
  row "$h: broken JSON" "$(chk $h '{"session_id": "x", broken')" ok
  row "$h: empty stdin" "$(chk $h '')" ok
done
row 'hook-post: unknown tool_name' "$(chk hook-post '{"session_id":"a1b2c3d4-0000-4000-8000-000000000009","tool_name":"Bash","tool_input":{"command":"ls"}}')" ok
row 'hook-post: no inbox for an unknown tool_name' "$(exists _inbox/a1b2c3d4-0000-4000-8000-000000000009.jsonl)" gone
row 'hook-post: tool_input is a string' "$(chk hook-post '{"session_id":"a1b2c3d4-0000-4000-8000-000000000009","tool_name":"mcp__claude-in-chrome__computer","tool_input":"x"}')" ok
row 'hook-post: batch with broken actions' "$(chk hook-post '{"session_id":"a1b2c3d4-0000-4000-8000-000000000009","tool_name":"mcp__computer-use__computer_batch","tool_input":{"actions":[1,"x",null,{"name":3,"input":"y"}]}}')" ok
row 'hook-post: session_id missing or containing path separators' "$(chk hook-post '{"session_id":"../../etc","tool_name":"mcp__claude-in-chrome__computer","tool_input":{}}')" ok
row 'hook-stop: no session_id' "$(chk hook-stop '{"hook_event_name":"Stop"}')" ok

rm -rf "$RUNBOOK_ROOT" "$SK" "$FAKE"
