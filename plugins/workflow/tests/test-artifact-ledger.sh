#!/bin/bash
# Live check of hooks/artifact-ledger.py on the oldest supported Python (3.9).
# Runs the real hook in a throwaway git repo (CLAUDE_PROJECT_DIR), so no real ledger is touched.
#
# Input shape: the documented PostToolUse payload (https://code.claude.com/docs/en/hooks:
# session_id, cwd, hook_event_name, tool_name, tool_input, tool_response, tool_use_id).
# Synthesized, NOT captured from a real Artifact run: the tool_response fields (artifact_id, url, title, path, ...)
# are the ones the hook reads, so every publish payload below is unverified against a live event.
# The tool_input fields `icon` (current) and `favicon` (deprecated) come from the Artifact tool's own input schema.
# The ledger line in case 5 is hand-written in the shape older versions of the hook wrote (key `favicon`).
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/artifact-ledger.py"
# Prefer the stock macOS interpreter (3.9); elsewhere fall back to python3 (CI pins 3.9 separately).
if [ -x /usr/bin/python3 ]; then PY=/usr/bin/python3; else PY=python3; fi
T=$(mktemp -d "${TMPDIR:-/tmp}/ledger-fixture.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
# Drop a repository or config inherited from the caller (GIT_DIR from a git hook, XDG or GIT_CONFIG_GLOBAL config)
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG_GLOBAL
git -C "$T" init -q 2>/dev/null
LEDGER="$T/.artifacts/ledger.jsonl"
INDEX="$T/.artifacts/index.html"

run() {  # $1 = stdin payload
  printf '%s' "$1" | CLAUDE_PROJECT_DIR="$T" "$PY" "$HOOK" >"$T/out" 2>"$T/err"
  echo $?
}
lines() { [ -f "$LEDGER" ] && wc -l <"$LEDGER" | tr -d ' ' || echo 0; }
check() {  # $1 label, $2 got, $3 want
  [ "$2" = "$3" ] && r=ok || r=ng
  echo "  $1: got '$2' -> $r (expect ok: '$3')"
}
# pub <id> <tool_input json> [<extra tool_response fields, starting with a comma>]: a publish payload
pub() {
  printf '{"session_id":"s1","cwd":"%s","hook_event_name":"PostToolUse","tool_name":"Artifact","tool_input":%s,"tool_response":{"artifact_id":"%s","url":"https://claude.ai/artifact/%s","title":"Page %s","version":"1"%s},"tool_use_id":"toolu_01"}' \
    "$T" "$2" "$1" "$1" "$1" "${3:-}"
}
# field <id> <key>: <key> of the last ledger row for artifact <id> ("(none)" when absent or null)
field() {
  "$PY" - "$LEDGER" "$1" "$2" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
rows = [r for r in rows if r.get("artifact_id") == sys.argv[2]]
v = rows[-1].get(sys.argv[3]) if rows else None
print("(none)" if v is None else v)
PY
}
# icon_cell <id>: the first-column text of the index.html row that links to artifact <id>
icon_cell() {
  "$PY" - "$INDEX" "$1" <<'PY'
import re, sys
m = re.search(r'<tr><td class="ic">([^<]*)</td><td><a href="https://claude\.ai/artifact/%s">' % re.escape(sys.argv[2]),
              open(sys.argv[1], encoding="utf-8").read())
print(m.group(1) if m else "(no row)")
PY
}

echo "=== case 1: Artifact publish appends one line ==="
PUB='{"session_id":"s1","cwd":"'"$T"'","hook_event_name":"PostToolUse","tool_name":"Artifact","tool_input":{"file_path":"'"$T"'/page.html","description":"A page","icon":"chart"},"tool_response":{"artifact_id":"abc123","url":"https://claude.ai/artifact/abc123","title":"Demo Page","version":"1"},"tool_use_id":"toolu_01"}'
rc=$(run "$PUB")
check "exit" "$rc" 0
check "ledger lines" "$(lines)" 1
check "stdout empty" "$(wc -c <"$T/out" | tr -d ' ')" 0
check "stderr empty" "$(wc -c <"$T/err" | tr -d ' ')" 0
"$PY" - "$LEDGER" <<'PY'
import json, sys
r = json.loads(open(sys.argv[1]).read().splitlines()[0])
ok = (r["event"] == "publish" and r["artifact_id"] == "abc123"
      and r["url"].endswith("/abc123") and r["title"] == "Demo Page"
      and r["src_path"] == "page.html")  # repo-relative, never absolute
print("  row fields -> %s (expect ok: publish / id / url / title / relative src_path)" % ("ok" if ok else "ng"))
PY
check "row fields script exit" "$?" 0
[ -f "$INDEX" ] && r=ok || r=ng; echo "  index.html -> $r (expect ok)"

echo "=== case 2: payloads the hook does not handle exit 0 and write nothing ==="
rm -rf "$T/.artifacts"
for p in '{}' \
         '{"tool_name":"Write","tool_input":{"file_path":"/x"},"tool_response":{"filePath":"/x","type":"create"}}' \
         '{"tool_name":"Artifact","tool_input":{},"tool_response":"plain text"}' \
         '{"tool_name":"Artifact","tool_input":{},"tool_response":{"artifacts":[{"url":"https://claude.ai/artifact/zzz","updatedAt":"2026-01-01T00:00:00Z"}]}}' \
         'not json'; do
  rc=$(run "$p")
  check "exit for ${p:0:40}" "$rc" 0
  check "  no ledger" "$([ -e "$LEDGER" ] && echo written || echo none)" none
  check "  stdout empty" "$(wc -c <"$T/out" | tr -d ' ')" 0
done

echo "=== case 3: the icon of a publish (icon is current, favicon deprecated) ==="
rm -rf "$T/.artifacts"
run "$(pub ic1 '{"file_path":"a.html","icon":"chart"}')" >/dev/null
check "icon only: recorded" "$(field ic1 favicon)" chart
check "icon only: shown in index.html" "$(icon_cell ic1)" chart
run "$(pub ic2 '{"file_path":"b.html","favicon":"calendar"}')" >/dev/null
check "favicon only: recorded" "$(field ic2 favicon)" calendar
run "$(pub ic3 '{"file_path":"c.html","icon":"map","favicon":"recipe"}')" >/dev/null
check "both passed: icon wins" "$(field ic3 favicon)" map
run "$(pub ic4 '{"file_path":"d.html"}')" >/dev/null
check "neither passed: nothing recorded" "$(field ic4 favicon)" "(none)"
check "neither passed: default glyph in index.html" "$(icon_cell ic4)" "📄"

echo "=== case 4: a redeploy that omits icon keeps the icon of the first publish ==="
run "$(pub ic1 '{"file_path":"a.html"}')" >/dev/null
check "ledger rows for ic1" "$(grep -c '"artifact_id": "ic1"' "$LEDGER")" 2
check "index.html still shows the first icon" "$(icon_cell ic1)" chart

echo "=== case 5: a row an older version wrote (favicon) still renders ==="
rm -rf "$T/.artifacts"; mkdir -p "$T/.artifacts"
printf '%s\n' '{"ts": "2026-10-01T09:00:00+09:00", "event": "publish", "artifact_id": "old1", "url": "https://claude.ai/artifact/old1", "title": "Old page", "description": null, "favicon": "📊", "updated": null, "version": "3", "src_path": "old.html", "session_id": "s0"}' >"$LEDGER"
rc=$(run '{"tool_name":"Artifact","tool_input":{},"tool_response":"plain text"}')   # nothing to append: rebuilds the missing index
check "exit" "$rc" 0
check "ledger untouched" "$(lines)" 1
check "index.html rebuilt with the old icon" "$(icon_cell old1)" "📊"

echo "=== case 6: src_path prefers the response's path and never writes an absolute path ==="
rm -rf "$T/.artifacts"
run "$(pub p1 '{"file_path":"'"$T"'/draft.html"}' ',"path":"'"$T"'/site/page.html"')" >/dev/null
check "response path inside the project: repo-relative" "$(field p1 src_path)" site/page.html
OUT=$(mktemp -d "${TMPDIR:-/tmp}/ledger-outside.XXXX") || exit 1
run "$(pub p2 '{"file_path":"'"$T"'/draft.html"}' ',"path":"'"$OUT"'/scratch/report.html"')" >/dev/null
rm -rf "$OUT"
check "response path outside the project: file name only" "$(field p2 src_path)" report.html
check "no src_path starts with /" "$(grep -c '"src_path": "/' "$LEDGER")" 0
check "the temp directory name is nowhere in the ledger" "$(grep -c -F -e "$(basename "$T")" -e "$(basename "$OUT")" "$LEDGER")" 0
