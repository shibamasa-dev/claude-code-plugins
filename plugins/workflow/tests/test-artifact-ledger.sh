#!/bin/bash
# Live check of hooks/artifact-ledger.py on the oldest supported Python (3.9).
# Runs the real hook in a throwaway git repo (CLAUDE_PROJECT_DIR), so no real ledger is touched.
#
# Input shape: the documented PostToolUse payload (https://code.claude.com/docs/en/hooks:
# session_id, cwd, hook_event_name, tool_name, tool_input, tool_response, tool_use_id).
# NOT captured from a real Artifact run: the tool_response fields (artifact_id, url, title, ...)
# are the ones the hook reads, so the publish payload below is unverified against a live event.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/artifact-ledger.py"
# Prefer the stock macOS interpreter (3.9); elsewhere fall back to python3 (CI pins 3.9 separately).
if [ -x /usr/bin/python3 ]; then PY=/usr/bin/python3; else PY=python3; fi
T=$(mktemp -d "${TMPDIR:-/tmp}/ledger-fixture.XXXX")
git -C "$T" init -q 2>/dev/null
LEDGER="$T/.artifacts/ledger.jsonl"

run() {  # $1 = stdin payload
  printf '%s' "$1" | CLAUDE_PROJECT_DIR="$T" "$PY" "$HOOK" >"$T/out" 2>"$T/err"
  echo $?
}
lines() { [ -f "$LEDGER" ] && wc -l <"$LEDGER" | tr -d ' ' || echo 0; }
check() {  # $1 label, $2 got, $3 want
  [ "$2" = "$3" ] && r=ok || r=ng
  echo "  $1: got '$2' -> $r (expect ok: '$3')"
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
[ -f "$T/.artifacts/index.html" ] && r=ok || r=ng; echo "  index.html -> $r (expect ok)"

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

rm -rf "$T"
